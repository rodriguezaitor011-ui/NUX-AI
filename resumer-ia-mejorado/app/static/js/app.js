// ========================================
// NUX IA v2.0 - GLASSMORPHISM
// JavaScript con cápsulas y status indicators
// ========================================

// Variables globales
let sources = [];
let activeSources = [];
let sessionId = null;
let chatHistory = [];
let currentTool = null;
let chatMode = 'sources';
let currentFlashcards = [];
let currentCardIndex = 0;
let toolOutputs = [];
let pendingFile = null;
let isProcessing = false;

// ========================================
// STATUS INDICATORS
// ========================================

function updateProcessingStatus(processing) {
    isProcessing = processing;
    const statusLeft = document.getElementById('status-left');
    const statusRight = document.getElementById('status-right');
    
    if (processing) {
        statusLeft?.classList.add('active');
        statusRight?.classList.add('active');
    } else {
        statusLeft?.classList.remove('active');
        statusRight?.classList.remove('active');
    }
}

// ========================================
// CAPSULE CONTROLS
// ========================================

function toggleCapsule(side) {
    const capsule = document.getElementById(`capsule-${side}`);
    capsule?.classList.toggle('expanded');
}

// Cerrar cápsulas con ESC
document.addEventListener('keydown', function(e) {
    if (e.key === 'Escape') {
        const sources = document.getElementById('capsule-sources');
        const tools = document.getElementById('capsule-tools');
        sources?.classList.remove('expanded');
        tools?.classList.remove('expanded');
    }
});

// ========================================
// GUARDAR EN HISTORIAL
// ========================================

async function guardarEnHistorial(mensaje, respuesta) {
    const token = localStorage.getItem('auth_token');
    if (!token) return;
    
    try {
        await fetch('/save-chat', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                token: token,
                message: mensaje,
                response: respuesta
            })
        });
    } catch (err) {
        console.error('Error guardando en historial:', err);
    }
}

// Dark mode
function toggleDark() {
    document.body.classList.toggle('dark');
    localStorage.setItem('dark-mode', document.body.classList.contains('dark'));
}

if (localStorage.getItem('dark-mode') === 'true') {
    document.body.classList.add('dark');
}

// ========================================
// CAMBIAR MODO DE CHAT
// ========================================

function cambiarModoChat(modo) {
    chatMode = modo;
    
    const subtitle = document.getElementById('chat-subtitle');
    const input = document.getElementById('chat-input');
    
    if (modo === 'sources') {
        subtitle.textContent = 'Powered by DeepSeek v3 • Respondiendo solo con tus fuentes';
        input.placeholder = 'Pregunta sobre tus documentos...';
        
        if (activeSources.length === 0) {
            agregarMensajeSistema('📚 Modo: Solo fuentes. Añade documentos para empezar.');
        }
    } else {
        subtitle.textContent = 'Powered by DeepSeek v3 • Chat general con conocimiento amplio';
        input.placeholder = 'Pregunta lo que quieras...';
        agregarMensajeSistema('🌐 Modo: Con internet. Puedo responder cualquier pregunta.');
    }
}

// ========================================
// GESTIÓN DE FUENTES
// ========================================

function addSource(input) {
    const file = input.files[0];
    if (!file) return;
    
    if (file.size > 10 * 1024 * 1024) {
        alert('El archivo es demasiado grande. Máximo 10MB.');
        input.value = '';
        return;
    }
    
    // Mostrar modal de renombrar
    mostrarRenameModal(file);
    
    input.value = '';
}

function renderSources() {
    const sourcesList = document.getElementById('sources-list');
    const emptyState = document.getElementById('empty-sources');
    
    if (sources.length === 0) {
        emptyState.style.display = 'block';
        sourcesList.innerHTML = '';
        return;
    }
    
    emptyState.style.display = 'none';
    
    sourcesList.innerHTML = sources.map(source => `
        <div class="source-item ${source.active ? 'active' : ''}" onclick="toggleSource('${source.id}')">
            <div class="source-header">
                <div class="source-name">
                    <span class="source-icon">${source.type === 'pdf' ? '📄' : '📝'}</span>
                    ${source.name}
                </div>
                <button class="source-remove" onclick="event.stopPropagation(); removeSource('${source.id}')">✕</button>
            </div>
            <div class="source-meta">${source.size} • ${source.active ? 'Activo' : 'Inactivo'}</div>
        </div>
    `).join('');
}

function toggleSource(sourceId) {
    const source = sources.find(s => s.id === sourceId);
    if (!source) return;
    
    source.active = !source.active;
    
    if (source.active) {
        activeSources.push(sourceId);
    } else {
        activeSources = activeSources.filter(id => id !== sourceId);
    }
    
    renderSources();
}

function removeSource(sourceId) {
    sources = sources.filter(s => s.id !== sourceId);
    activeSources = activeSources.filter(id => id !== sourceId);
    renderSources();
    
    if (sources.length === 0) {
        agregarMensajeSistema('No quedan fuentes activas. Añade documentos para continuar.');
    }
}

function formatFileSize(bytes) {
    if (bytes < 1024) return bytes + ' B';
    if (bytes < 1024 * 1024) return (bytes / 1024).toFixed(1) + ' KB';
    return (bytes / (1024 * 1024)).toFixed(1) + ' MB';
}

// ========================================
// MODAL: Renombrar archivo
// ========================================

function mostrarRenameModal(file) {
    pendingFile = file;
    
    const modal = document.getElementById('rename-modal');
    const input = document.getElementById('rename-input');
    const filenameDiv = document.getElementById('original-filename');
    
    const nombreSinExtension = file.name.replace(/\.[^/.]+$/, '');
    input.value = nombreSinExtension;
    filenameDiv.textContent = `Archivo original: ${file.name}`;
    
    modal.classList.add('active');
    input.focus();
    input.select();
    
    input.onkeypress = function(e) {
        if (e.key === 'Enter') {
            confirmarRename();
        }
    };
}

function cerrarRenameModal() {
    const modal = document.getElementById('rename-modal');
    modal.classList.remove('active');
    pendingFile = null;
}

function confirmarRename() {
    const input = document.getElementById('rename-input');
    const nuevoNombre = input.value.trim();
    
    if (!nuevoNombre) {
        alert('Por favor, ingresa un nombre para el documento');
        return;
    }
    
    if (!pendingFile) return;
    
    const sourceId = Date.now().toString();
    const source = {
        id: sourceId,
        name: nuevoNombre,
        originalName: pendingFile.name,
        type: pendingFile.name.endsWith('.pdf') ? 'pdf' : 'txt',
        size: formatFileSize(pendingFile.size),
        active: true,
        file: pendingFile,
        content: null
    };
    
    sources.push(source);
    activeSources.push(sourceId);
    renderSources();
    
    if (pendingFile.name.endsWith('.txt')) {
        const reader = new FileReader();
        reader.onload = function(e) {
            source.content = e.target.result;
            console.log(`📄 ${nuevoNombre} cargado: ${source.content.length} caracteres`);
            agregarMensajeSistema(`📄 ${nuevoNombre} añadido (${source.size})`);
        };
        reader.readAsText(pendingFile);
    } else if (pendingFile.name.endsWith('.pdf')) {
        agregarMensajeSistema(`📄 ${nuevoNombre} añadido - se procesará al usar herramientas`);
    }
    
    cerrarRenameModal();
}

// ========================================
// MODAL: Pegar texto
// ========================================

function mostrarPasteModal() {
    const modal = document.getElementById('paste-modal');
    const nameInput = document.getElementById('paste-name-input');
    const contentInput = document.getElementById('paste-content');
    
    nameInput.value = '';
    contentInput.value = '';
    
    modal.classList.add('active');
    nameInput.focus();
}

function cerrarPasteModal() {
    const modal = document.getElementById('paste-modal');
    modal.classList.remove('active');
}

async function confirmarPaste() {
    const nameInput = document.getElementById('paste-name-input');
    const contentInput = document.getElementById('paste-content');
    
    const nombre = nameInput.value.trim();
    const contenido = contentInput.value.trim();
    
    if (!nombre) {
        alert('Por favor, ingresa un nombre para el documento');
        return;
    }
    
    if (!contenido) {
        alert('Por favor, pega el texto o enlace');
        return;
    }
    
    const esURL = contenido.startsWith('http://') || contenido.startsWith('https://');
    
    if (esURL) {
        agregarMensajeSistema('⚠️ Extracción de enlaces aún no implementada. Pega el texto directamente por ahora.');
        return;
    }
    
    const sourceId = Date.now().toString();
    const source = {
        id: sourceId,
        name: nombre,
        type: 'txt',
        size: formatFileSize(contenido.length),
        active: true,
        file: null,
        content: contenido
    };
    
    sources.push(source);
    activeSources.push(sourceId);
    renderSources();
    
    agregarMensajeSistema(`📄 ${nombre} añadido (${source.size})`);
    
    cerrarPasteModal();
}

// Cerrar modales con click fuera
document.addEventListener('click', function(e) {
    if (e.target.classList.contains('modal-overlay')) {
        if (e.target.id === 'rename-modal') {
            cerrarRenameModal();
        } else if (e.target.id === 'paste-modal') {
            cerrarPasteModal();
        }
    }
});

// ========================================
// CHAT
// ========================================

function enviarMensaje() {
    const input = document.getElementById('chat-input');
    const mensaje = input.value.trim();
    
    if (!mensaje) return;
    
    if (chatMode === 'sources' && activeSources.length === 0) {
        agregarMensajeSistema('⚠️ Añade al menos un documento antes de hacer preguntas en modo "Solo fuentes"');
        return;
    }
    
    agregarMensajeUsuario(mensaje);
    input.value = '';
    autoResize(input);
    
    if (chatMode === 'sources') {
        procesarMensaje(mensaje);
    } else {
        procesarMensajeGeneral(mensaje);
    }
}

async function procesarMensajeGeneral(mensaje) {
    updateProcessingStatus(true);
    mostrarIndicador('DeepSeek v3 está pensando...');
    
    const messageDiv = crearMensajeAsistenteVacio('DeepSeek v3');
    const contentDiv = messageDiv.querySelector('.message-content');
    
    try {
        const response = await fetch('/chat-general-stream', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
            },
            body: JSON.stringify({
                pregunta: mensaje,
                historial: chatHistory
            })
        });
        
        ocultarIndicador();
        
        if (!response.ok) {
            throw new Error('Error en la respuesta del servidor');
        }
        
        const reader = response.body.getReader();
        const decoder = new TextDecoder();
        let respuestaCompleta = '';
        
        while (true) {
            const { done, value } = await reader.read();
            
            if (done) break;
            
            const chunk = decoder.decode(value);
            const lines = chunk.split('\n');
            
            for (const line of lines) {
                if (line.startsWith('data: ')) {
                    const data = line.slice(6);
                    
                    if (data === '[DONE]') {
                        chatHistory.push({ pregunta: mensaje, respuesta: respuestaCompleta });
                        await guardarEnHistorial(mensaje, respuestaCompleta);
                        updateProcessingStatus(false);
                        return;
                    }
                    
                    try {
                        const json = JSON.parse(data);
                        if (json.content) {
                            respuestaCompleta += json.content;
                            contentDiv.innerHTML = marked.parse(respuestaCompleta);
                            const messages = document.getElementById('chat-messages');
                            messages.scrollTop = messages.scrollHeight;
                        }
                    } catch (e) {
                        // Ignorar
                    }
                }
            }
        }
        
    } catch (error) {
        console.error('Error en chat general:', error);
        ocultarIndicador();
        updateProcessingStatus(false);
        messageDiv.remove();
        agregarMensajeSistema('Error al conectar con el servidor');
    }
}

async function procesarMensaje(mensaje) {
    updateProcessingStatus(true);
    mostrarIndicador('DeepSeek v3 está pensando...');
    
    try {
        const fuentesActivas = sources.filter(s => activeSources.includes(s.id));
        
        if (!sessionId) {
            await procesarDocumentos(fuentesActivas);
        }
        
        const response = await fetch('/chat', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
            },
            body: JSON.stringify({
                session_id: sessionId,
                pregunta: mensaje,
                historial: chatHistory
            })
        });
        
        const data = await response.json();
        
        ocultarIndicador();
        updateProcessingStatus(false);
        
        if (data.respuesta) {
            agregarMensajeAsistente(data.respuesta, data.modelo || 'DeepSeek v3');
            chatHistory.push({ pregunta: mensaje, respuesta: data.respuesta });
            await guardarEnHistorial(mensaje, data.respuesta);
        } else if (data.error) {
            agregarMensajeSistema(`Error: ${data.error}`);
        }
        
    } catch (error) {
        console.error('Error en chat:', error);
        ocultarIndicador();
        updateProcessingStatus(false);
        agregarMensajeSistema('Error al conectar con el servidor');
    }
}

async function procesarDocumentos(fuentes) {
    // Esta función solo se usa internamente, no actualiza status
    
    try {
        let contenidoCombinado = '';
        
        for (const fuente of fuentes) {
            if (fuente.type === 'pdf') {
                contenidoCombinado += `[PDF: ${fuente.name}]\n\n`;
            } else {
                contenidoCombinado += fuente.content + '\n\n';
            }
        }
        
        const formData = new FormData();
        formData.append('texto', contenidoCombinado);
        formData.append('modo', 'general');
        formData.append('task', 'summary');
        
        const response = await fetch('/resumir', {
            method: 'POST',
            body: formData
        });
        
        const html = await response.text();
        const parser = new DOMParser();
        const doc = parser.parseFromString(html, 'text/html');
        const sessionInput = doc.getElementById('session-id');
        
        if (sessionInput) {
            sessionId = sessionInput.value;
        }
        
    } catch (error) {
        console.error('Error procesando documentos:', error);
    }
}

// ========================================
// HERRAMIENTAS
// ========================================

async function ejecutarHerramienta(herramienta) {
    if (activeSources.length === 0) {
        agregarMensajeSistema('⚠️ Necesitas añadir documentos primero');
        return;
    }
    
    const mensajesHerramienta = {
        'resumir': '📝 Genera un resumen ejecutivo de los documentos',
        'flashcards': '🎴 Crea flashcards para estudiar',
        'analizar': '📊 Analiza la estructura y conceptos clave'
    };
    
    const mensaje = mensajesHerramienta[herramienta] || `Ejecutar: ${herramienta}`;
    agregarMensajeUsuario(mensaje);
    
    updateProcessingStatus(true);
    mostrarIndicador(`Ejecutando ${herramienta}...`);
    
    try {
        const fuentesActivas = sources.filter(s => activeSources.includes(s.id));
        
        const formData = new FormData();
        
        const pdfSource = fuentesActivas.find(f => f.type === 'pdf');
        if (pdfSource && pdfSource.file) {
            formData.append('archivo', pdfSource.file);
            console.log(`📄 Enviando PDF: ${pdfSource.name}`);
        } else {
            let contenido = '';
            for (const fuente of fuentesActivas) {
                if (fuente.content) {
                    contenido += fuente.content + '\n\n';
                }
            }
            
            if (!contenido.trim()) {
                ocultarIndicador();
                updateProcessingStatus(false);
                agregarMensajeSistema('⚠️ No hay contenido en las fuentes');
                return;
            }
            
            formData.append('texto', contenido);
        }
        
        formData.append('modo', herramienta === 'resumir' ? 'general' : 'estudiar');
        formData.append('task', herramienta === 'flashcards' ? 'flashcards' : 'summary');
        
        console.log(`🔧 Ejecutando: ${herramienta}, task: ${herramienta === 'flashcards' ? 'flashcards' : 'summary'}`);
        
        const response = await fetch('/resumir', {
            method: 'POST',
            headers: {
                'Accept': 'application/json'
            },
            body: formData
        });
        
        const data = await response.json();
        
        ocultarIndicador();
        updateProcessingStatus(false);
        
        if (herramienta === 'flashcards' && data.flashcards) {
            mostrarFlashcardsVisuales(data.flashcards);
            
            const nombreOutput = 'Flashcards';
            añadirOutput('flashcards', nombreOutput, data.flashcards);
            await guardarEnHistorial(mensaje, data.flashcards);
            
        } else if (data.resumen) {
            agregarMensajeAsistente(data.resumen, data.modelo || 'NXUS o.0.1');
            
            const nombreOutput = {
                'resumir': 'Resumen ejecutivo',
                'analizar': 'Análisis estructural'
            };
            añadirOutput(herramienta, nombreOutput[herramienta] || 'Output', data.resumen);
            await guardarEnHistorial(mensaje, data.resumen);
            
        } else if (data.error) {
            agregarMensajeSistema(`Error: ${data.error}`);
        }
        
    } catch (error) {
        console.error('Error ejecutando herramienta:', error);
        ocultarIndicador();
        updateProcessingStatus(false);
        agregarMensajeSistema('Error al ejecutar la herramienta');
    }
}

// ========================================
// FLASHCARDS VISUALES
// ========================================

function parsearFlashcards(texto) {
    const cards = [];
    const lineas = texto.split('\n');
    
    let currentCard = null;
    
    for (let linea of lineas) {
        linea = linea.trim();
        
        if (linea.startsWith('TARJETA') || linea.match(/^\d+\./)) {
            if (currentCard && currentCard.pregunta && currentCard.respuesta) {
                cards.push(currentCard);
            }
            currentCard = { pregunta: '', respuesta: '' };
        } else if (linea.startsWith('Pregunta:')) {
            if (currentCard) {
                currentCard.pregunta = linea.replace('Pregunta:', '').trim();
            }
        } else if (linea.startsWith('Respuesta:')) {
            if (currentCard) {
                currentCard.respuesta = linea.replace('Respuesta:', '').trim();
            }
        }
    }
    
    if (currentCard && currentCard.pregunta && currentCard.respuesta) {
        cards.push(currentCard);
    }
    
    return cards;
}

function mostrarFlashcardsVisuales(flashcardsTexto) {
    currentFlashcards = parsearFlashcards(flashcardsTexto);
    currentCardIndex = 0;
    
    if (currentFlashcards.length === 0) {
        agregarMensajeSistema('No se pudieron generar flashcards');
        return;
    }
    
    const messages = document.getElementById('chat-messages');
    
    const div = document.createElement('div');
    div.className = 'flashcards-container';
    div.innerHTML = `
        <div class="flashcards-header">
            <h3>🎴 Flashcards generadas (${currentFlashcards.length} tarjetas)</h3>
            <div class="flashcards-controls">
                <button class="btn-export" onclick="exportarFlashcards()">📥 Exportar a Anki</button>
            </div>
        </div>
        
        <div class="flashcard-viewer">
            <div class="flashcard" id="current-flashcard" onclick="flipCard()">
                <div class="flashcard-inner">
                    <div class="flashcard-front">
                        <div class="flashcard-label">Pregunta</div>
                        <div class="flashcard-content" id="card-front"></div>
                    </div>
                    <div class="flashcard-back">
                        <div class="flashcard-label">Respuesta</div>
                        <div class="flashcard-content" id="card-back"></div>
                    </div>
                </div>
            </div>
            
            <div class="flashcard-navigation">
                <button class="btn-nav" onclick="previousCard()" id="prev-btn">← Anterior</button>
                <span class="card-counter" id="card-counter">1 / ${currentFlashcards.length}</span>
                <button class="btn-nav" onclick="nextCard()" id="next-btn">Siguiente →</button>
            </div>
        </div>
    `;
    
    messages.appendChild(div);
    messages.scrollTop = messages.scrollHeight;
    
    renderCurrentCard();
}

function renderCurrentCard() {
    if (currentFlashcards.length === 0) return;
    
    const card = currentFlashcards[currentCardIndex];
    document.getElementById('card-front').textContent = card.pregunta;
    document.getElementById('card-back').textContent = card.respuesta;
    document.getElementById('card-counter').textContent = `${currentCardIndex + 1} / ${currentFlashcards.length}`;
    
    const flashcard = document.getElementById('current-flashcard');
    flashcard.classList.remove('flipped');
    
    document.getElementById('prev-btn').disabled = currentCardIndex === 0;
    document.getElementById('next-btn').disabled = currentCardIndex === currentFlashcards.length - 1;
}

function flipCard() {
    const flashcard = document.getElementById('current-flashcard');
    flashcard.classList.toggle('flipped');
}

function nextCard() {
    if (currentCardIndex < currentFlashcards.length - 1) {
        currentCardIndex++;
        renderCurrentCard();
    }
}

function previousCard() {
    if (currentCardIndex > 0) {
        currentCardIndex--;
        renderCurrentCard();
    }
}

function exportarFlashcards() {
    let ankiText = '';
    
    for (const card of currentFlashcards) {
        ankiText += `${card.pregunta}\t${card.respuesta}\n`;
    }
    
    const blob = new Blob([ankiText], { type: 'text/plain' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = 'flashcards_anki.txt';
    a.click();
    URL.revokeObjectURL(url);
    
    agregarMensajeSistema('📥 Flashcards exportadas. Importa el archivo en Anki con formato: Texto separado por tabuladores');
}

// ========================================
// GESTIÓN DE OUTPUTS
// ========================================

function añadirOutput(tipo, nombre, contenido) {
    const output = {
        id: Date.now().toString(),
        tipo: tipo,
        nombre: nombre,
        contenido: contenido,
        timestamp: new Date()
    };
    
    toolOutputs.push(output);
    renderOutputs();
}

function renderOutputs() {
    const outputSection = document.getElementById('tool-outputs');
    const outputList = document.getElementById('output-list');
    
    if (toolOutputs.length === 0) {
        outputSection.style.display = 'none';
        return;
    }
    
    outputSection.style.display = 'block';
    
    const iconos = {
        'resumir': '📝',
        'flashcards': '🎴',
        'analizar': '📊'
    };
    
    outputList.innerHTML = toolOutputs.slice(-5).reverse().map(output => {
        const tiempo = formatTiempo(output.timestamp);
        return `
            <div class="output-item" onclick="verOutput('${output.id}')">
                <span class="output-icon">${iconos[output.tipo] || '📄'}</span>
                <span class="output-name">${output.nombre}</span>
                <span class="output-time">${tiempo}</span>
            </div>
        `;
    }).join('');
}

function verOutput(outputId) {
    const output = toolOutputs.find(o => o.id === outputId);
    if (!output) return;
    
    if (output.tipo === 'flashcards') {
        mostrarFlashcardsVisuales(output.contenido);
    } else {
        agregarMensajeAsistente(output.contenido, 'NXUS o.0.1');
    }
}

function formatTiempo(timestamp) {
    const ahora = new Date();
    const diff = Math.floor((ahora - timestamp) / 1000);
    
    if (diff < 60) return 'Ahora';
    if (diff < 3600) return `${Math.floor(diff / 60)}m`;
    if (diff < 86400) return `${Math.floor(diff / 3600)}h`;
    return `${Math.floor(diff / 86400)}d`;
}

// ========================================
// MENSAJES DEL CHAT
// ========================================

function agregarMensajeUsuario(texto) {
    const messages = document.getElementById('chat-messages');
    
    const welcome = messages.querySelector('.welcome-message');
    if (welcome) welcome.remove();
    
    const div = document.createElement('div');
    div.className = 'chat-message user';
    div.innerHTML = `<div class="message-bubble">${escapeHtml(texto)}</div>`;
    messages.appendChild(div);
    messages.scrollTop = messages.scrollHeight;
}

function agregarMensajeAsistente(texto, modelo = 'DeepSeek v3') {
    const messages = document.getElementById('chat-messages');
    
    const div = document.createElement('div');
    div.className = 'chat-message assistant';
    div.innerHTML = `
        <div class="message-bubble">
            <div class="model-badge">${modelo}</div>
            <div class="message-content">${marked.parse(texto)}</div>
        </div>
    `;
    messages.appendChild(div);
    messages.scrollTop = messages.scrollHeight;
}

function crearMensajeAsistenteVacio(modelo = 'DeepSeek v3') {
    const messages = document.getElementById('chat-messages');
    
    const div = document.createElement('div');
    div.className = 'chat-message assistant';
    div.innerHTML = `
        <div class="message-bubble">
            <div class="model-badge">${modelo}</div>
            <div class="message-content"><span class="typing-indicator">●●●</span></div>
        </div>
    `;
    messages.appendChild(div);
    messages.scrollTop = messages.scrollHeight;
    
    return div;
}

function agregarMensajeSistema(texto) {
    const messages = document.getElementById('chat-messages');
    
    const div = document.createElement('div');
    div.className = 'chat-message system';
    div.innerHTML = `<div class="message-bubble" style="background: rgba(255,255,255,0.05); font-size: 13px; color: var(--muted);">${escapeHtml(texto)}</div>`;
    messages.appendChild(div);
    messages.scrollTop = messages.scrollHeight;
}

function limpiarChat() {
    const messages = document.getElementById('chat-messages');
    messages.innerHTML = '<div class="welcome-message"><div class="welcome-icon">👋</div><h3>Nueva conversación</h3></div>';
    chatHistory = [];
    sessionId = null;
}

// ========================================
// INDICADORES
// ========================================

function mostrarIndicador(texto) {
    const indicator = document.getElementById('processing-indicator');
    const indicatorText = document.getElementById('processing-text');
    
    indicatorText.textContent = texto;
    indicator.style.display = 'flex';
    
    const sendBtn = document.getElementById('send-btn');
    if (sendBtn) sendBtn.disabled = true;
}

function ocultarIndicador() {
    const indicator = document.getElementById('processing-indicator');
    indicator.style.display = 'none';
    
    const sendBtn = document.getElementById('send-btn');
    if (sendBtn) sendBtn.disabled = false;
}

// ========================================
// UTILIDADES
// ========================================

function escapeHtml(text) {
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
}

function autoResize(textarea) {
    textarea.style.height = 'auto';
    textarea.style.height = Math.min(textarea.scrollHeight, 120) + 'px';
}

const chatInput = document.getElementById('chat-input');
if (chatInput) {
    chatInput.addEventListener('input', function() {
        autoResize(this);
    });
}

// ========================================
// INICIALIZACIÓN
// ========================================

const sessionInput = document.getElementById('session-id');
if (sessionInput && sessionInput.value) {
    sessionId = sessionInput.value;
}

console.log('🎨 NUX IA v2.0 Glassmorphism cargado ✅');
// ========================================
// MOBILE ENHANCEMENTS
// Añadir al final de app.js
// ========================================

// Detectar si es móvil
const isMobile = window.innerWidth <= 768;

// ========================================
// GESTURES PARA CÁPSULAS EN MÓVIL
// ========================================

if (isMobile) {
    let touchStartY = 0;
    let touchEndY = 0;
    
    const capsule = document.getElementById('capsule-sources');
    
    if (capsule) {
        // Swipe up para abrir
        capsule.addEventListener('touchstart', (e) => {
            touchStartY = e.touches[0].clientY;
        }, { passive: true });
        
        capsule.addEventListener('touchend', (e) => {
            touchEndY = e.changedTouches[0].clientY;
            handleSwipe();
        }, { passive: true });
        
        function handleSwipe() {
            const swipeDistance = touchStartY - touchEndY;
            const isExpanded = capsule.classList.contains('expanded');
            
            // Swipe up (>50px) para abrir
            if (swipeDistance > 50 && !isExpanded) {
                toggleCapsule('sources');
            }
            // Swipe down (>50px) para cerrar
            else if (swipeDistance < -50 && isExpanded) {
                toggleCapsule('sources');
            }
        }
    }
    
    // Cerrar cápsulas al tocar fuera
    document.addEventListener('touchstart', (e) => {
        const capsuleSources = document.getElementById('capsule-sources');
        
        if (capsuleSources && capsuleSources.classList.contains('expanded')) {
            if (!capsuleSources.contains(e.target)) {
                toggleCapsule('sources');
            }
        }
    });
}

// ========================================
// AUTO-SCROLL EN CHAT MOBILE
// ========================================

function scrollToBottom() {
    const messages = document.getElementById('chat-messages');
    if (messages && isMobile) {
        // Smooth scroll en móvil
        messages.scrollTo({
            top: messages.scrollHeight,
            behavior: 'smooth'
        });
    }
}

// Llamar después de añadir mensajes
const originalAgregarMensaje = agregarMensajeUsuario;
agregarMensajeUsuario = function(texto) {
    originalAgregarMensaje(texto);
    setTimeout(scrollToBottom, 100);
};

// ========================================
// KEYBOARD HANDLING EN MÓVIL
// ========================================

if (isMobile) {
    const chatInput = document.getElementById('chat-input');
    
    if (chatInput) {
        // Prevenir scroll al abrir teclado
        chatInput.addEventListener('focus', () => {
            setTimeout(() => {
                chatInput.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
            }, 300);
        });
        
        // Cerrar cápsulas al abrir teclado
        chatInput.addEventListener('focus', () => {
            const capsuleSources = document.getElementById('capsule-sources');
            if (capsuleSources && capsuleSources.classList.contains('expanded')) {
                toggleCapsule('sources');
            }
        });
    }
}

// ========================================
// OPTIMIZACIÓN DE PERFORMANCE EN MÓVIL
// ========================================

if (isMobile) {
    // Throttle para resize
    let resizeTimeout;
    window.addEventListener('resize', () => {
        clearTimeout(resizeTimeout);
        resizeTimeout = setTimeout(() => {
            // Reinicializar iconos lucide después de resize
            if (typeof lucide !== 'undefined') {
                lucide.createIcons();
            }
        }, 250);
    });
    
    // Prevenir bounce en iOS
    document.body.addEventListener('touchmove', (e) => {
        if (e.target.closest('.chat-messages') || 
            e.target.closest('.sources-content') || 
            e.target.closest('.tools-content')) {
            // Permitir scroll en estos elementos
            return;
        }
        // Prevenir en el resto
        e.preventDefault();
    }, { passive: false });
}

// ========================================
// BOTTOM NAV MOBILE - ICONOS ACTUALIZADOS
// ========================================

function updateMobileBottomNav() {
    if (!isMobile) return;
    
    const capsule = document.getElementById('capsule-sources');
    if (!capsule) return;
    
    const collapsed = capsule.querySelector('.capsule-collapsed');
    if (!collapsed) return;
    
    // Reemplazar contenido para móvil
    collapsed.innerHTML = `
        <div class="capsule-icon" onclick="toggleCapsule('sources')" title="Fuentes">
            <i data-lucide="folder-open"></i>
        </div>
        <div class="capsule-icon" onclick="ejecutarHerramienta('resumir')" title="Resumir">
            <i data-lucide="file-text"></i>
        </div>
        <div class="capsule-icon" onclick="ejecutarHerramienta('flashcards')" title="Flashcards">
            <i data-lucide="layers"></i>
        </div>
        <div class="capsule-icon" onclick="ejecutarHerramienta('analizar')" title="Analizar">
            <i data-lucide="bar-chart-3"></i>
        </div>
    `;
    
    // Reinicializar iconos
    if (typeof lucide !== 'undefined') {
        lucide.createIcons();
    }
}

// Ejecutar al cargar
if (isMobile) {
    updateMobileBottomNav();
}

// ========================================
// PREVENIR ZOOM ACCIDENTAL EN iOS
// ========================================

document.addEventListener('gesturestart', function(e) {
    e.preventDefault();
});

document.addEventListener('gesturechange', function(e) {
    e.preventDefault();
});

document.addEventListener('gestureend', function(e) {
    e.preventDefault();
});

console.log('📱 Mobile enhancements loaded');

/* ========================================
   POMODORO TIMER - NUX IA
   Añadir al final de app.js
   ======================================== */

// ========================================
// POMODORO TIMER
// ========================================

let pomodoroInterval = null;
let pomodoroSeconds = 25 * 60; // 25 minutos
let pomodoroMode = 'work'; // 'work' o 'break'
let pomodoroSessions = 0;
let isPomodoroRunning = false;

// Cargar sesiones guardadas
function loadPomodoroStats() {
    const stats = localStorage.getItem('pomodoro_stats');
    if (stats) {
        const data = JSON.parse(stats);
        pomodoroSessions = data.sessions || 0;
        updatePomodoroStats();
    }
}

// Guardar sesiones
function savePomodoroStats() {
    localStorage.setItem('pomodoro_stats', JSON.stringify({
        sessions: pomodoroSessions,
        lastSession: new Date().toISOString()
    }));
}

// Toggle Pomodoro
function togglePomodoro() {
    const widget = document.getElementById('pomodoro-widget');
    if (!widget) {
        createPomodoroWidget();
    } else {
        widget.classList.toggle('minimized');
    }
}

// Crear widget
function createPomodoroWidget() {
    // Eliminar si ya existe
    const existing = document.getElementById('pomodoro-widget');
    if (existing) {
        existing.remove();
    }
    
    const widget = document.createElement('div');
    widget.id = 'pomodoro-widget';
    widget.className = 'pomodoro-widget';
    widget.innerHTML = `
        <div class="pomodoro-header">
            <div class="pomodoro-title">
                <i data-lucide="clock" style="width:16px;height:16px;"></i>
                <span>Pomodoro Timer</span>
            </div>
            <div class="pomodoro-actions">
                <button onclick="minimizePomodoro()" class="pomodoro-btn-icon" title="Minimizar">
                    <i data-lucide="minus" style="width:14px;height:14px;"></i>
                </button>
                <button onclick="closePomodoro()" class="pomodoro-btn-icon" title="Cerrar">
                    <i data-lucide="x" style="width:14px;height:14px;"></i>
                </button>
            </div>
        </div>
        
        <div class="pomodoro-body">
            <div class="pomodoro-mode" id="pomodoro-mode">Tiempo de estudio</div>
            
            <div class="pomodoro-circle">
                <svg class="pomodoro-progress" viewBox="0 0 100 100">
                    <circle cx="50" cy="50" r="45" class="pomodoro-progress-bg"></circle>
                    <circle cx="50" cy="50" r="45" class="pomodoro-progress-bar" id="pomodoro-progress"></circle>
                </svg>
                <div class="pomodoro-time" id="pomodoro-time">25:00</div>
            </div>
            
            <div class="pomodoro-controls">
                <button onclick="startPomodoro()" class="pomodoro-btn primary" id="start-btn">
                    <i data-lucide="play" style="width:16px;height:16px;"></i>
                    Iniciar
                </button>
                <button onclick="pausePomodoro()" class="pomodoro-btn" id="pause-btn" style="display:none;">
                    <i data-lucide="pause" style="width:16px;height:16px;"></i>
                    Pausar
                </button>
                <button onclick="resetPomodoro()" class="pomodoro-btn">
                    <i data-lucide="rotate-ccw" style="width:16px;height:16px;"></i>
                    Reset
                </button>
            </div>
            
            <div class="pomodoro-stats">
                <div class="stat-item">
                    <i data-lucide="check-circle" style="width:14px;height:14px;"></i>
                    <span id="sessions-count">0</span> sesiones hoy
                </div>
            </div>
        </div>
    `;
    
    document.body.appendChild(widget);
    
    // Inicializar iconos
    if (typeof lucide !== 'undefined') {
        lucide.createIcons();
    }
    
    loadPomodoroStats();
}

// Start
function startPomodoro() {
    if (isPomodoroRunning) return;
    
    isPomodoroRunning = true;
    
    document.getElementById('start-btn').style.display = 'none';
    document.getElementById('pause-btn').style.display = 'flex';
    
    pomodoroInterval = setInterval(() => {
        pomodoroSeconds--;
        updatePomodoroDisplay();
        
        if (pomodoroSeconds <= 0) {
            finishPomodoro();
        }
    }, 1000);
}

// Pause
function pausePomodoro() {
    isPomodoroRunning = false;
    clearInterval(pomodoroInterval);
    
    document.getElementById('start-btn').style.display = 'flex';
    document.getElementById('pause-btn').style.display = 'none';
}

// Reset
function resetPomodoro() {
    pausePomodoro();
    
    if (pomodoroMode === 'work') {
        pomodoroSeconds = 25 * 60;
    } else {
        pomodoroSeconds = 5 * 60;
    }
    
    updatePomodoroDisplay();
}

// Finish
function finishPomodoro() {
    pausePomodoro();
    
    // Reproducir sonido
    playPomodoroSound();
    
    if (pomodoroMode === 'work') {
        // Completó sesión de trabajo
        pomodoroSessions++;
        savePomodoroStats();
        updatePomodoroStats();
        
        // Cambiar a descanso
        pomodoroMode = 'break';
        pomodoroSeconds = 5 * 60;
        document.getElementById('pomodoro-mode').textContent = '☕ Tiempo de descanso';
        
        // Notificación
        showPomodoroNotification('¡Sesión completada! 🎉', 'Toma un descanso de 5 minutos');
    } else {
        // Completó descanso
        pomodoroMode = 'work';
        pomodoroSeconds = 25 * 60;
        document.getElementById('pomodoro-mode').textContent = '📚 Tiempo de estudio';
        
        showPomodoroNotification('¡Descanso terminado! 💪', 'Volvamos al trabajo');
    }
    
    updatePomodoroDisplay();
}

// Update display
function updatePomodoroDisplay() {
    const minutes = Math.floor(pomodoroSeconds / 60);
    const seconds = pomodoroSeconds % 60;
    
    const timeStr = `${minutes.toString().padStart(2, '0')}:${seconds.toString().padStart(2, '0')}`;
    document.getElementById('pomodoro-time').textContent = timeStr;
    
    // Update progress circle
    const totalSeconds = pomodoroMode === 'work' ? 25 * 60 : 5 * 60;
    const progress = ((totalSeconds - pomodoroSeconds) / totalSeconds) * 100;
    
    const circle = document.getElementById('pomodoro-progress');
    const circumference = 2 * Math.PI * 45;
    const offset = circumference - (progress / 100) * circumference;
    
    circle.style.strokeDashoffset = offset;
}

// Update stats
function updatePomodoroStats() {
    document.getElementById('sessions-count').textContent = pomodoroSessions;
}

// Sound
function playPomodoroSound() {
    // Crear tono simple con Web Audio API
    const audioContext = new (window.AudioContext || window.webkitAudioContext)();
    const oscillator = audioContext.createOscillator();
    const gainNode = audioContext.createGain();
    
    oscillator.connect(gainNode);
    gainNode.connect(audioContext.destination);
    
    oscillator.frequency.value = 800;
    oscillator.type = 'sine';
    
    gainNode.gain.setValueAtTime(0.3, audioContext.currentTime);
    gainNode.gain.exponentialRampToValueAtTime(0.01, audioContext.currentTime + 0.5);
    
    oscillator.start(audioContext.currentTime);
    oscillator.stop(audioContext.currentTime + 0.5);
}

// Notification
function showPomodoroNotification(title, message) {
    // Crear notificación visual
    const notification = document.createElement('div');
    notification.className = 'pomodoro-notification';
    notification.innerHTML = `
        <div class="notification-content">
            <h4>${title}</h4>
            <p>${message}</p>
        </div>
    `;
    
    document.body.appendChild(notification);
    
    setTimeout(() => {
        notification.classList.add('show');
    }, 100);
    
    setTimeout(() => {
        notification.classList.remove('show');
        setTimeout(() => notification.remove(), 300);
    }, 3000);
    
    // Notificación del navegador (si tiene permisos)
    if ('Notification' in window && Notification.permission === 'granted') {
        new Notification(title, {
            body: message,
            icon: '/static/icon.png'
        });
    }
}

// Minimize
function minimizePomodoro() {
    document.getElementById('pomodoro-widget').classList.add('minimized');
}

// Close
function closePomodoro() {
    pausePomodoro();
    document.getElementById('pomodoro-widget').remove();
}

// Request notification permission
function requestNotificationPermission() {
    if ('Notification' in window && Notification.permission === 'default') {
        Notification.requestPermission();
    }
}

// Initialize on load
loadPomodoroStats();

console.log('⏱️ Pomodoro Timer loaded');

/* ========================================
   MAPAS MENTALES - FRONTEND
   Añadir al final de app.js
   ======================================== */

// ========================================
// MINDMAP VIEWER
// ========================================

let currentMindmap = null;

// Mostrar mapa mental
function mostrarMapaMental(mermaidCode) {
    currentMindmap = mermaidCode;
    
    const messages = document.getElementById('chat-messages');
    
    const div = document.createElement('div');
    div.className = 'mindmap-container';
    div.innerHTML = `
        <div class="mindmap-header">
            <h3>🗺️ Mapa Mental Generado</h3>
            <div class="mindmap-controls">
                <button class="btn-mindmap" onclick="zoomInMindmap()">
                    <i data-lucide="zoom-in" style="width:16px;height:16px;"></i>
                    Zoom +
                </button>
                <button class="btn-mindmap" onclick="zoomOutMindmap()">
                    <i data-lucide="zoom-out" style="width:16px;height:16px;"></i>
                    Zoom -
                </button>
                <button class="btn-mindmap" onclick="resetZoomMindmap()">
                    <i data-lucide="maximize" style="width:16px;height:16px;"></i>
                    Reset
                </button>
                <button class="btn-mindmap primary" onclick="exportMindmap()">
                    <i data-lucide="download" style="width:16px;height:16px;"></i>
                    Exportar
                </button>
            </div>
        </div>
        
        <div class="mindmap-viewer" id="mindmap-viewer">
            <div class="mindmap-loading">
                <div class="spinner"></div>
                <p>Renderizando mapa mental...</p>
            </div>
        </div>
        
        <div class="mindmap-footer">
            <p>💡 Tip: Usa los controles de zoom para explorar el mapa</p>
        </div>
    `;
    
    messages.appendChild(div);
    messages.scrollTop = messages.scrollHeight;
    
    // Renderizar Mermaid
    renderMermaid(mermaidCode);
    
    // Reinicializar iconos
    if (typeof lucide !== 'undefined') {
        lucide.createIcons();
    }
}

// Renderizar Mermaid
async function renderMermaid(code) {
    const viewer = document.getElementById('mindmap-viewer');
    
    try {
        // Inicializar Mermaid si no está
        if (typeof mermaid === 'undefined') {
            await loadMermaid();
        }
        
        // Configurar Mermaid
        mermaid.initialize({
            startOnLoad: false,
            theme: document.body.classList.contains('dark') ? 'dark' : 'default',
            themeVariables: {
                primaryColor: '#de4cf5',
                primaryTextColor: '#fff',
                primaryBorderColor: '#c94dd1',
                lineColor: '#de4cf5',
                secondaryColor: '#8b5cf6',
                tertiaryColor: '#6366f1',
                background: document.body.classList.contains('dark') ? '#1a1a2e' : '#ffffff',
                mainBkg: document.body.classList.contains('dark') ? '#2a2a3e' : '#f8f9fb',
                nodeBorder: '#de4cf5',
                clusterBkg: document.body.classList.contains('dark') ? '#2a2a3e' : '#f8f9fb',
                fontSize: '14px',
                fontFamily: '-apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif'
            },
            mindmap: {
                padding: 20,
                useMaxWidth: false
            }
        });
        
        // Generar ID único
        const id = 'mermaid-' + Date.now();
        
        // Renderizar
        const { svg } = await mermaid.render(id, code);
        
        viewer.innerHTML = `
            <div class="mindmap-svg-container" id="svg-container">
                ${svg}
            </div>
        `;
        
        // Hacer el mapa draggable
        makeMindmapDraggable();
        
    } catch (error) {
        console.error('Error rendering mermaid:', error);
        viewer.innerHTML = `
            <div class="mindmap-error">
                <i data-lucide="alert-circle" style="width:48px;height:48px;color:#ef4444;"></i>
                <h4>Error al renderizar mapa mental</h4>
                <p>${error.message}</p>
                <button class="btn-retry" onclick="renderMermaid(\`${code.replace(/`/g, '\\`')}\`)">
                    Reintentar
                </button>
            </div>
        `;
        
        if (typeof lucide !== 'undefined') {
            lucide.createIcons();
        }
    }
}

// Cargar librería Mermaid
function loadMermaid() {
    return new Promise((resolve, reject) => {
        if (typeof mermaid !== 'undefined') {
            resolve();
            return;
        }
        
        const script = document.createElement('script');
        script.src = 'https://cdn.jsdelivr.net/npm/mermaid@10/dist/mermaid.min.js';
        script.onload = resolve;
        script.onerror = reject;
        document.head.appendChild(script);
    });
}

// Zoom controls
let currentZoom = 1;

function zoomInMindmap() {
    currentZoom += 0.2;
    applyZoom();
}

function zoomOutMindmap() {
    if (currentZoom > 0.4) {
        currentZoom -= 0.2;
        applyZoom();
    }
}

function resetZoomMindmap() {
    currentZoom = 1;
    applyZoom();
}

function applyZoom() {
    const container = document.getElementById('svg-container');
    if (container) {
        container.style.transform = `scale(${currentZoom})`;
    }
}

// Draggable
let isDragging = false;
let startX, startY, scrollLeft, scrollTop;

function makeMindmapDraggable() {
    const viewer = document.getElementById('mindmap-viewer');
    if (!viewer) return;
    
    viewer.style.cursor = 'grab';
    
    viewer.addEventListener('mousedown', (e) => {
        isDragging = true;
        viewer.style.cursor = 'grabbing';
        startX = e.pageX - viewer.offsetLeft;
        startY = e.pageY - viewer.offsetTop;
        scrollLeft = viewer.scrollLeft;
        scrollTop = viewer.scrollTop;
    });
    
    viewer.addEventListener('mouseleave', () => {
        isDragging = false;
        viewer.style.cursor = 'grab';
    });
    
    viewer.addEventListener('mouseup', () => {
        isDragging = false;
        viewer.style.cursor = 'grab';
    });
    
    viewer.addEventListener('mousemove', (e) => {
        if (!isDragging) return;
        e.preventDefault();
        const x = e.pageX - viewer.offsetLeft;
        const y = e.pageY - viewer.offsetTop;
        const walkX = (x - startX) * 2;
        const walkY = (y - startY) * 2;
        viewer.scrollLeft = scrollLeft - walkX;
        viewer.scrollTop = scrollTop - walkY;
    });
}

// Exportar mapa
async function exportMindmap() {
    try {
        const svg = document.querySelector('#svg-container svg');
        if (!svg) {
            alert('No hay mapa mental para exportar');
            return;
        }
        
        // Obtener dimensiones
        const bbox = svg.getBBox();
        const width = bbox.width + 40;
        const height = bbox.height + 40;
        
        // Crear canvas
        const canvas = document.createElement('canvas');
        canvas.width = width * 2; // 2x para mejor calidad
        canvas.height = height * 2;
        const ctx = canvas.getContext('2d');
        
        // Fondo
        ctx.fillStyle = document.body.classList.contains('dark') ? '#1a1a2e' : '#ffffff';
        ctx.fillRect(0, 0, canvas.width, canvas.height);
        
        // Convertir SVG a imagen
        const svgData = new XMLSerializer().serializeToString(svg);
        const svgBlob = new Blob([svgData], { type: 'image/svg+xml;charset=utf-8' });
        const url = URL.createObjectURL(svgBlob);
        
        const img = new Image();
        img.onload = function() {
            ctx.drawImage(img, 20, 20, width * 2 - 40, height * 2 - 40);
            
            // Descargar
            canvas.toBlob(function(blob) {
                const url = URL.createObjectURL(blob);
                const a = document.createElement('a');
                a.href = url;
                a.download = 'mapa-mental-nux-ia.png';
                a.click();
                URL.revokeObjectURL(url);
            });
            
            URL.revokeObjectURL(url);
        };
        img.src = url;
        
        agregarMensajeSistema('📥 Mapa mental exportado como imagen PNG');
        
    } catch (error) {
        console.error('Error exporting mindmap:', error);
        alert('Error al exportar mapa mental');
    }
}

// Integración con herramientas
async function ejecutarHerramientaMindmap() {
    if (activeSources.length === 0) {
        agregarMensajeSistema('⚠️ Necesitas añadir documentos primero');
        return;
    }
    
    agregarMensajeUsuario('🗺️ Genera un mapa mental del contenido');
    
    updateProcessingStatus(true);
    mostrarIndicador('Generando mapa mental...');
    
    try {
        const fuentesActivas = sources.filter(s => activeSources.includes(s.id));
        
        const formData = new FormData();
        
        const pdfSource = fuentesActivas.find(f => f.type === 'pdf');
        if (pdfSource && pdfSource.file) {
            formData.append('archivo', pdfSource.file);
        } else {
            let contenido = '';
            for (const fuente of fuentesActivas) {
                if (fuente.content) {
                    contenido += fuente.content + '\n\n';
                }
            }
            
            if (!contenido.trim()) {
                ocultarIndicador();
                updateProcessingStatus(false);
                agregarMensajeSistema('⚠️ No hay contenido en las fuentes');
                return;
            }
            
            formData.append('texto', contenido);
        }
        
        formData.append('modo', 'general');
        formData.append('task', 'mindmap');
        
        const response = await fetch('/resumir', {
            method: 'POST',
            headers: {
                'Accept': 'application/json'
            },
            body: formData
        });
        
        const data = await response.json();
        
        ocultarIndicador();
        updateProcessingStatus(false);
        
        if (data.mindmap) {
            mostrarMapaMental(data.mindmap);
            añadirOutput('mindmap', 'Mapa Mental', data.mindmap);
        } else if (data.error) {
            agregarMensajeSistema(`Error: ${data.error}`);
        }
        
    } catch (error) {
        console.error('Error generando mapa mental:', error);
        ocultarIndicador();
        updateProcessingStatus(false);
        agregarMensajeSistema('Error al generar mapa mental');
    }
}

console.log('🗺️ Mindmap viewer loaded');

/* ========================================
   NOTAS Y HIGHLIGHTS - MEJORADO
   Reemplazar en app.js
   ======================================== */

// ========================================
// HIGHLIGHTS & NOTES SYSTEM
// ========================================

let highlights = [];
let currentSelection = null;

// Cargar highlights guardados
function loadHighlights() {
    const saved = localStorage.getItem('nux_highlights');
    if (saved) {
        try {
            highlights = JSON.parse(saved);
            console.log('✅ Highlights cargados:', highlights.length);
        } catch (e) {
            console.error('Error cargando highlights:', e);
            highlights = [];
        }
    }
}

// Guardar highlights
function saveHighlights() {
    localStorage.setItem('nux_highlights', JSON.stringify(highlights));
    updateHighlightsBadge();
}

// Manejar selección de texto
function handleTextSelection(e) {
    // No mostrar menú si se clickeó en el menú mismo o en highlights
    if (e.target.closest('.highlight-menu') || e.target.closest('.btn-highlights')) {
        return;
    }
    
    const selection = window.getSelection();
    const selectedText = selection.toString().trim();
    
    // Verificar que el texto esté en área válida
    if (selectedText.length < 10) {
        hideHighlightMenu();
        return;
    }
    
    // Verificar que esté en área de mensajes o resumen
    const validContainer = selection.anchorNode?.parentElement?.closest('.chat-messages, .message-bubble, .resumen-content');
    
    if (!validContainer) {
        hideHighlightMenu();
        return;
    }
    
    currentSelection = {
        text: selectedText,
        anchorNode: selection.anchorNode,
        anchorOffset: selection.anchorOffset,
        focusNode: selection.focusNode,
        focusOffset: selection.focusOffset
    };
    
    showHighlightMenu(e.pageX, e.pageY);
}

// Mostrar menú de highlight
function showHighlightMenu(x, y) {
    hideHighlightMenu();
    
    const menu = document.createElement('div');
    menu.id = 'highlight-menu';
    menu.className = 'highlight-menu';
    
    // Ajustar posición si está muy cerca del borde
    const maxX = window.innerWidth - 250;
    const maxY = window.innerHeight - 100;
    
    menu.style.left = Math.min(x, maxX) + 'px';
    menu.style.top = Math.min(y + 10, maxY) + 'px';
    
    menu.innerHTML = `
        <div class="highlight-colors">
            <button class="highlight-btn yellow" onclick="addHighlight('yellow')" title="Amarillo">
                <i data-lucide="highlighter" style="width:16px;height:16px;"></i>
            </button>
            <button class="highlight-btn green" onclick="addHighlight('green')" title="Verde">
                <i data-lucide="highlighter" style="width:16px;height:16px;"></i>
            </button>
            <button class="highlight-btn blue" onclick="addHighlight('blue')" title="Azul">
                <i data-lucide="highlighter" style="width:16px;height:16px;"></i>
            </button>
            <button class="highlight-btn red" onclick="addHighlight('red')" title="Rojo">
                <i data-lucide="highlighter" style="width:16px;height:16px;"></i>
            </button>
            <button class="highlight-btn note" onclick="addHighlightWithNote()" title="Con nota">
                <i data-lucide="sticky-note" style="width:16px;height:16px;"></i>
            </button>
        </div>
    `;
    
    document.body.appendChild(menu);
    
    if (typeof lucide !== 'undefined') {
        lucide.createIcons();
    }
}

// Ocultar menú
function hideHighlightMenu() {
    const menu = document.getElementById('highlight-menu');
    if (menu) {
        menu.remove();
    }
}

// Añadir highlight
function addHighlight(color) {
    if (!currentSelection) {
        console.log('❌ No hay selección');
        return;
    }
    
    const highlight = {
        id: Date.now(),
        text: currentSelection.text,
        color: color,
        note: '',
        timestamp: new Date().toISOString()
    };
    
    highlights.push(highlight);
    saveHighlights();
    
    console.log('✅ Highlight añadido:', highlight);
    
    hideHighlightMenu();
    window.getSelection().removeAllRanges();
    
    // Mostrar feedback
    showHighlightFeedback(color);
    updateHighlightsPanel();
}

// Añadir highlight con nota
function addHighlightWithNote() {
    if (!currentSelection) return;
    
    hideHighlightMenu();
    
    const note = prompt('Añade una nota (opcional):');
    
    const highlight = {
        id: Date.now(),
        text: currentSelection.text,
        color: 'yellow',
        note: note || '',
        timestamp: new Date().toISOString()
    };
    
    highlights.push(highlight);
    saveHighlights();
    
    console.log('✅ Highlight con nota añadido:', highlight);
    
    window.getSelection().removeAllRanges();
    showHighlightFeedback('yellow');
    updateHighlightsPanel();
}

// Mostrar feedback visual
function showHighlightFeedback(color) {
    const feedback = document.createElement('div');
    feedback.className = 'highlight-feedback';
    feedback.style.cssText = `
        position: fixed;
        top: 50%;
        left: 50%;
        transform: translate(-50%, -50%);
        background: var(--panel-bg);
        backdrop-filter: blur(12px);
        border: 2px solid var(--primary);
        border-radius: 12px;
        padding: 20px 40px;
        box-shadow: 0 8px 24px rgba(0, 0, 0, 0.3);
        z-index: 10001;
        animation: fadeInOut 1.5s ease;
        font-weight: 600;
        display: flex;
        align-items: center;
        gap: 12px;
    `;
    
    const colorNames = {
        yellow: '🟡 Amarillo',
        green: '🟢 Verde',
        blue: '🔵 Azul',
        red: '🔴 Rojo'
    };
    
    feedback.innerHTML = `
        <i data-lucide="check-circle" style="width:24px;height:24px;color:var(--primary);"></i>
        <span>Highlight guardado: ${colorNames[color]}</span>
    `;
    
    document.body.appendChild(feedback);
    
    if (typeof lucide !== 'undefined') {
        lucide.createIcons();
    }
    
    setTimeout(() => {
        feedback.remove();
    }, 1500);
}

// Panel de highlights
function toggleHighlightsPanel() {
    let panel = document.getElementById('highlights-panel');
    
    if (panel) {
        panel.classList.toggle('open');
    } else {
        createHighlightsPanel();
    }
}

function createHighlightsPanel() {
    const panel = document.createElement('div');
    panel.id = 'highlights-panel';
    panel.className = 'highlights-panel open';
    
    panel.innerHTML = `
        <div class="highlights-header">
            <h3>
                <i data-lucide="bookmark" style="width:18px;height:18px;"></i>
                Mis Highlights
            </h3>
            <div class="highlights-actions">
                <button onclick="exportHighlights()" class="btn-icon" title="Exportar">
                    <i data-lucide="download" style="width:16px;height:16px;"></i>
                </button>
                <button onclick="clearAllHighlights()" class="btn-icon" title="Borrar todos">
                    <i data-lucide="trash-2" style="width:16px;height:16px;"></i>
                </button>
                <button onclick="toggleHighlightsPanel()" class="btn-icon" title="Cerrar">
                    <i data-lucide="x" style="width:16px;height:16px;"></i>
                </button>
            </div>
        </div>
        <div class="highlights-list" id="highlights-list"></div>
    `;
    
    document.body.appendChild(panel);
    
    if (typeof lucide !== 'undefined') {
        lucide.createIcons();
    }
    
    updateHighlightsPanel();
}

// Actualizar panel
function updateHighlightsPanel() {
    const list = document.getElementById('highlights-list');
    if (!list) return;
    
    if (highlights.length === 0) {
        list.innerHTML = `
            <div class="empty-highlights">
                <i data-lucide="highlighter" style="width:48px;height:48px;opacity:0.3;"></i>
                <p>No tienes highlights</p>
                <small>Selecciona texto para añadir</small>
            </div>
        `;
        if (typeof lucide !== 'undefined') {
            lucide.createIcons();
        }
        return;
    }
    
    const sorted = [...highlights].sort((a, b) => new Date(b.timestamp) - new Date(a.timestamp));
    
    list.innerHTML = sorted.map(h => {
        const date = new Date(h.timestamp).toLocaleDateString('es-ES', {
            month: 'short',
            day: 'numeric',
            hour: '2-digit',
            minute: '2-digit'
        });
        
        return `
            <div class="highlight-item highlight-${h.color}">
                <div class="highlight-text">${h.text}</div>
                ${h.note ? `<div class="highlight-note">📝 ${h.note}</div>` : ''}
                <div class="highlight-meta">
                    ${date}
                    <button onclick="editHighlightNote(${h.id})" class="btn-edit" title="Editar nota">
                        <i data-lucide="edit-2" style="width:12px;height:12px;"></i>
                    </button>
                    <button onclick="deleteHighlight(${h.id})" class="btn-delete-small" title="Eliminar">
                        <i data-lucide="trash-2" style="width:12px;height:12px;"></i>
                    </button>
                </div>
            </div>
        `;
    }).join('');
    
    if (typeof lucide !== 'undefined') {
        lucide.createIcons();
    }
}

// Editar nota
function editHighlightNote(id) {
    const highlight = highlights.find(h => h.id === id);
    if (!highlight) return;
    
    const newNote = prompt('Nota:', highlight.note);
    if (newNote !== null) {
        highlight.note = newNote;
        saveHighlights();
        updateHighlightsPanel();
    }
}

// Eliminar highlight
function deleteHighlight(id) {
    if (!confirm('¿Eliminar este highlight?')) return;
    
    highlights = highlights.filter(h => h.id !== id);
    saveHighlights();
    updateHighlightsPanel();
}

// Exportar highlights
function exportHighlights() {
    if (highlights.length === 0) {
        alert('No tienes highlights para exportar');
        return;
    }
    
    let text = '# MIS HIGHLIGHTS - NUX IA\n\n';
    text += `Exportado: ${new Date().toLocaleString('es-ES')}\n`;
    text += `Total: ${highlights.length} highlights\n\n`;
    text += '---\n\n';
    
    highlights.forEach((h, i) => {
        text += `## ${i + 1}. ${h.text}\n`;
        if (h.note) {
            text += `**Nota:** ${h.note}\n`;
        }
        text += `*Color: ${h.color}*\n`;
        text += `*Fecha: ${new Date(h.timestamp).toLocaleString('es-ES')}*\n\n`;
    });
    
    const blob = new Blob([text], { type: 'text/plain' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `nux-highlights-${Date.now()}.txt`;
    a.click();
    URL.revokeObjectURL(url);
}

// Borrar todos
function clearAllHighlights() {
    if (!confirm(`¿Borrar todos los ${highlights.length} highlights? Esta acción no se puede deshacer.`)) {
        return;
    }
    
    highlights = [];
    saveHighlights();
    updateHighlightsPanel();
}

// Actualizar badge
function updateHighlightsBadge() {
    const badge = document.getElementById('highlights-badge');
    if (badge) {
        const count = highlights.length;
        badge.textContent = count;
        badge.style.display = count > 0 ? 'block' : 'none';
    }
}

// Inicializar
document.addEventListener('DOMContentLoaded', () => {
    loadHighlights();
    document.addEventListener('mouseup', handleTextSelection);
    updateHighlightsBadge();
});

// Cerrar menú al hacer scroll o click fuera
document.addEventListener('scroll', hideHighlightMenu, true);
document.addEventListener('mousedown', (e) => {
    if (!e.target.closest('.highlight-menu')) {
        hideHighlightMenu();
    }
});

// Animación feedback
const style = document.createElement('style');
style.textContent = `
@keyframes fadeInOut {
    0% { opacity: 0; transform: translate(-50%, -50%) scale(0.8); }
    20% { opacity: 1; transform: translate(-50%, -50%) scale(1); }
    80% { opacity: 1; transform: translate(-50%, -50%) scale(1); }
    100% { opacity: 0; transform: translate(-50%, -50%) scale(0.8); }
}
`;
document.head.appendChild(style);

console.log('📝 Highlights & Notes system loaded (improved)');
