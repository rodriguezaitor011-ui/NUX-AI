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
// FETCH WITH AUTHORIZATION
// ========================================

async function fetchWithAuth(url, options = {}) {
    const token = localStorage.getItem('auth_token');
    const headers = { ...options.headers };
    if (token) headers['Authorization'] = `Bearer ${token}`;
    const response = await fetch(url, { ...options, headers });
    if (response.status === 401) {
        console.warn('⚠️ Token expirado. Redirigiendo a login...');
        localStorage.removeItem('auth_token');
        localStorage.removeItem('refresh_token');
        window.location.href = '/login';
    }
    return response;
}

// ========================================
// GUARDAR EN HISTORIAL
// ========================================

async function guardarEnHistorial(mensaje, respuesta) {
    const token = localStorage.getItem('auth_token');
    if (!token) return;
    try {
        await fetchWithAuth('/save-chat', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ message: mensaje, response: respuesta })
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
    mostrarRenameModal(file);
    input.value = '';
}

// ========================================
// RENDER SOURCES — con estado de procesado
// ========================================

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
        <div class="source-item ${source.active ? 'active' : ''}" 
             onclick="toggleSource('${source.id}')">
            <div class="source-header">
                <div class="source-name">
                    <span class="source-icon">
                        ${source.processed 
                            ? '✅' 
                            : source.processing 
                                ? '⏳' 
                                : source.type === 'pdf' ? '📄' : '📝'
                        }
                    </span>
                    ${source.name}
                </div>
                <button class="source-remove" 
                        onclick="event.stopPropagation(); removeSource('${source.id}')">✕</button>
            </div>
            <div class="source-meta">
                ${source.size} • 
                ${source.processed 
                    ? '<span style="color:#10b981;font-weight:600">✓ Listo para preguntas</span>'
                    : source.processing 
                        ? '<span style="color:var(--primary)">Procesando...</span>'
                        : '<span style="color:var(--muted)">Pendiente</span>'
                }
            </div>
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
// AUTO-PROCESAR DOCUMENTO AL AÑADIR
// Como NotebookLM — sin pasos extra
// ========================================

async function autoProcessSource(source) {
    // Marcar como procesando
    source.processing = true;
    source.processed = false;
    renderSources();

    // Quitar el welcome message si existe
    const welcome = document.getElementById('chat-messages')?.querySelector('.welcome-message');
    if (welcome) welcome.remove();

    agregarMensajeSistema(`⏳ Analizando "${source.name}"...`);
    updateProcessingStatus(true);
    mostrarIndicador(`Procesando "${source.name}"...`);

    try {
        const formData = new FormData();

        if (source.type === 'pdf' && source.file) {
            formData.append('archivo', source.file);
        } else if (source.content) {
            formData.append('texto', source.content);
        } else {
            throw new Error('No hay contenido para procesar');
        }

        formData.append('modo', 'general');
        formData.append('task', 'summary');

        const response = await fetch('/resumir', {
            method: 'POST',
            headers: { 'Accept': 'application/json' },
            body: formData
        });

        const data = await response.json();

        ocultarIndicador();
        updateProcessingStatus(false);

        if (data.session_id) {
            sessionId = data.session_id;

            // Marcar fuente como procesada
            source.processing = false;
            source.processed = true;
            renderSources();

            agregarMensajeSistema(
                `✅ "${source.name}" listo. Puedes hacer preguntas sobre él.`
            );

            // Mostrar resumen automáticamente en el chat
            if (data.resumen) {
                agregarMensajeAsistente(data.resumen, 'NXUS o.0.1');
                añadirOutput('resumir', `Resumen — ${source.name}`, data.resumen);
            }

        } else if (data.error) {
            source.processing = false;
            source.processed = false;
            renderSources();
            agregarMensajeSistema(`❌ Error procesando "${source.name}": ${data.error}`);
        }

    } catch (error) {
        console.error('Error en autoProcess:', error);
        source.processing = false;
        source.processed = false;
        renderSources();
        ocultarIndicador();
        updateProcessingStatus(false);
        agregarMensajeSistema(`❌ Error al procesar "${source.name}". Intenta usar el botón Resumir manualmente.`);
    }
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
        if (e.key === 'Enter') confirmarRename();
    };
}

function cerrarRenameModal() {
    document.getElementById('rename-modal').classList.remove('active');
    pendingFile = null;
}

// ← MODIFICADO: auto-procesa al confirmar
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
        processed: false,
        processing: false,
        file: pendingFile,
        content: null
    };

    sources.push(source);
    activeSources.push(sourceId);
    renderSources();
    cerrarRenameModal();

    if (pendingFile.name.endsWith('.txt')) {
        const reader = new FileReader();
        reader.onload = function(e) {
            source.content = e.target.result;
            // ← AUTO-PROCESAR
            autoProcessSource(source);
        };
        reader.readAsText(pendingFile);
    } else if (pendingFile.name.endsWith('.pdf')) {
        // ← AUTO-PROCESAR
        autoProcessSource(source);
    }
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
    document.getElementById('paste-modal').classList.remove('active');
}

// ← MODIFICADO: auto-procesa al confirmar
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
        agregarMensajeSistema('⚠️ Extracción de enlaces aún no implementada. Pega el texto directamente.');
        return;
    }

    const sourceId = Date.now().toString();
    const source = {
        id: sourceId,
        name: nombre,
        type: 'txt',
        size: formatFileSize(contenido.length),
        active: true,
        processed: false,
        processing: false,
        file: null,
        content: contenido
    };

    sources.push(source);
    activeSources.push(sourceId);
    renderSources();
    cerrarPasteModal();

    // ← AUTO-PROCESAR
    autoProcessSource(source);
}

// Cerrar modales con click fuera
document.addEventListener('click', function(e) {
    if (e.target.classList.contains('modal-overlay')) {
        if (e.target.id === 'rename-modal') cerrarRenameModal();
        else if (e.target.id === 'paste-modal') cerrarPasteModal();
        else if (e.target.id === 'ocr-modal') cerrarOCRModal();
    }
});

// ========================================
// MODAL: OCR Escanear apuntes
// ========================================

let pendingOCRFile = null;

function mostrarOCRModal() {
    const modal = document.getElementById('ocr-modal');
    const previewWrap = document.getElementById('ocr-preview-wrap');
    const loading = document.getElementById('ocr-loading');
    const errDiv = document.getElementById('ocr-error');
    const submitBtn = document.getElementById('ocr-submit-btn');
    const fileInput = document.getElementById('ocr-file');
    pendingOCRFile = null;
    fileInput.value = '';
    previewWrap.style.display = 'none';
    loading.style.display = 'none';
    errDiv.style.display = 'none';
    errDiv.textContent = '';
    submitBtn.disabled = true;
    modal.classList.add('active');
    setTimeout(() => lucide.createIcons(), 100);
}

function cerrarOCRModal() {
    document.getElementById('ocr-modal').classList.remove('active');
    pendingOCRFile = null;
}

function onOCRFileSelect(input) {
    const file = input.files[0];
    const previewWrap = document.getElementById('ocr-preview-wrap');
    const preview = document.getElementById('ocr-preview');
    const filenameEl = document.getElementById('ocr-filename');
    const submitBtn = document.getElementById('ocr-submit-btn');
    const errDiv = document.getElementById('ocr-error');
    errDiv.style.display = 'none';
    errDiv.textContent = '';
    if (!file) {
        previewWrap.style.display = 'none';
        submitBtn.disabled = true;
        pendingOCRFile = null;
        return;
    }
    const validTypes = ['image/jpeg', 'image/png', 'image/webp', 'image/gif'];
    if (!validTypes.includes(file.type)) {
        errDiv.textContent = 'Formato no permitido. Usa JPG, PNG, WebP o GIF.';
        errDiv.style.display = 'block';
        submitBtn.disabled = true;
        pendingOCRFile = null;
        return;
    }
    const maxMb = 10;
    if (file.size > maxMb * 1024 * 1024) {
        errDiv.textContent = 'La imagen es demasiado grande. Máximo ' + maxMb + ' MB.';
        errDiv.style.display = 'block';
        submitBtn.disabled = true;
        pendingOCRFile = null;
        return;
    }
    pendingOCRFile = file;
    filenameEl.textContent = file.name + ' (' + formatFileSize(file.size) + ')';
    preview.src = URL.createObjectURL(file);
    preview.onload = function() { URL.revokeObjectURL(this.src); };
    previewWrap.style.display = 'block';
    submitBtn.disabled = false;
}

// ← MODIFICADO: auto-procesa tras OCR
async function confirmarOCR() {
    if (!pendingOCRFile) return;
    const loading = document.getElementById('ocr-loading');
    const errDiv = document.getElementById('ocr-error');
    const submitBtn = document.getElementById('ocr-submit-btn');
    errDiv.style.display = 'none';
    errDiv.textContent = '';
    loading.style.display = 'block';
    submitBtn.disabled = true;

    try {
        const formData = new FormData();
        formData.append('image', pendingOCRFile);
        const response = await fetch('/api/ocr-image', {
            method: 'POST',
            body: formData
        });
        const data = await response.json().catch(() => ({}));
        if (!response.ok) throw new Error(data.error || 'Error al extraer el texto');
        if (!data.text || !data.text.trim()) throw new Error('No se detectó texto en la imagen');

        const sourceId = Date.now().toString();
        const name = 'Apuntes escaneados ' + new Date().toLocaleDateString('es-ES', {
            day: '2-digit', month: '2-digit', hour: '2-digit', minute: '2-digit'
        });
        const source = {
            id: sourceId,
            name: name,
            type: 'txt',
            size: formatFileSize(data.text.length),
            active: true,
            processed: false,
            processing: false,
            file: null,
            content: data.text.trim()
        };

        sources.push(source);
        activeSources.push(sourceId);
        renderSources();
        cerrarOCRModal();

        // ← AUTO-PROCESAR
        autoProcessSource(source);

    } catch (err) {
        errDiv.textContent = err.message || 'Error al procesar la imagen';
        errDiv.style.display = 'block';
        submitBtn.disabled = true;
    } finally {
        loading.style.display = 'none';
        if (pendingOCRFile) submitBtn.disabled = false;
    }
}

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

    // Bloquear si hay documentos procesándose
    if (chatMode === 'sources' && sources.some(s => s.processing)) {
        agregarMensajeSistema('⏳ Espera a que termine de procesar el documento...');
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
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ pregunta: mensaje, historial: chatHistory })
        });
        ocultarIndicador();
        if (!response.ok) throw new Error('Error en la respuesta del servidor');
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
                    } catch (e) { /* ignorar */ }
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
    mostrarIndicador('Consultando documentos...');

    try {
        // Si no hay sessionId y hay fuentes sin procesar, avisar
        if (!sessionId) {
            const fuentesSinProcesar = sources.filter(s => activeSources.includes(s.id) && !s.processed);
            if (fuentesSinProcesar.length > 0) {
                ocultarIndicador();
                updateProcessingStatus(false);
                agregarMensajeSistema(
                    '⚠️ Los documentos aún no están listos. ' +
                    'Espera a que terminen de procesarse o usa el botón "Resumir".'
                );
                return;
            }
        }

        const response = await fetch('/chat', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                session_id: sessionId,
                question: mensaje,
                mode: chatMode,
                history: chatHistory.slice(-5)
            })
        });

        const data = await response.json();
        ocultarIndicador();
        updateProcessingStatus(false);

        if (data.answer) {
            if (!data.has_context && chatMode === 'sources') {
                agregarMensajeSistema(
                    '⚠️ Respondo con conocimiento general porque no hay contexto cargado. ' +
                    'Usa "Resumir" para activarlo.'
                );
            }
            agregarMensajeAsistente(data.answer, 'DeepSeek v3');
            chatHistory.push({ pregunta: mensaje, respuesta: data.answer });
            await guardarEnHistorial(mensaje, data.answer);
        } else if (data.error) {
            agregarMensajeSistema(`❌ Error: ${data.error}`);
        }

    } catch (error) {
        console.error('Error en chat:', error);
        ocultarIndicador();
        updateProcessingStatus(false);
        agregarMensajeSistema('❌ Error al conectar con el servidor');
    }
}

async function procesarDocumentos(fuentes) {
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
        const response = await fetch('/resumir', { method: 'POST', body: formData });
        const html = await response.text();
        const parser = new DOMParser();
        const doc = parser.parseFromString(html, 'text/html');
        const sessionInput = doc.getElementById('session-id');
        if (sessionInput && sessionInput.value) {
            sessionId = sessionInput.value;
            console.log('💾 Session ID obtenido:', sessionId);
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
        } else {
            let contenido = '';
            for (const fuente of fuentesActivas) {
                if (fuente.content) contenido += fuente.content + '\n\n';
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
        const response = await fetch('/resumir', {
            method: 'POST',
            headers: { 'Accept': 'application/json' },
            body: formData
        });
        const data = await response.json();
        ocultarIndicador();
        updateProcessingStatus(false);
        if (data.session_id) {
            sessionId = data.session_id;
            console.log('💾 Session ID actualizado tras herramienta:', sessionId);
        }
        if (herramienta === 'flashcards' && data.flashcards) {
            mostrarFlashcardsVisuales(data.flashcards);
            añadirOutput('flashcards', 'Flashcards', data.flashcards);
            await guardarEnHistorial(mensaje, data.flashcards);
        } else if (data.resumen) {
            agregarMensajeAsistente(data.resumen, data.modelo || 'NXUS o.0.1');
            const nombreOutput = { 'resumir': 'Resumen ejecutivo', 'analizar': 'Análisis estructural' };
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
            if (currentCard) currentCard.pregunta = linea.replace('Pregunta:', '').trim();
        } else if (linea.startsWith('Respuesta:')) {
            if (currentCard) currentCard.respuesta = linea.replace('Respuesta:', '').trim();
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
    document.getElementById('current-flashcard').classList.remove('flipped');
    document.getElementById('prev-btn').disabled = currentCardIndex === 0;
    document.getElementById('next-btn').disabled = currentCardIndex === currentFlashcards.length - 1;
}

function flipCard() {
    document.getElementById('current-flashcard').classList.toggle('flipped');
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
    toolOutputs.push({
        id: Date.now().toString(),
        tipo, nombre, contenido,
        timestamp: new Date()
    });
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
    const iconos = { 'resumir': '📝', 'flashcards': '🎴', 'analizar': '📊' };
    outputList.innerHTML = toolOutputs.slice(-5).reverse().map(output => `
        <div class="output-item" onclick="verOutput('${output.id}')">
            <span class="output-icon">${iconos[output.tipo] || '📄'}</span>
            <span class="output-name">${output.nombre}</span>
            <span class="output-time">${formatTiempo(output.timestamp)}</span>
        </div>
    `).join('');
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
    const diff = Math.floor((new Date() - timestamp) / 1000);
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
    messages.innerHTML = `
        <div class="welcome-message">
            <div class="welcome-icon">👋</div>
            <h3>Nueva conversación</h3>
            <p style="color:var(--muted);font-size:14px;margin-top:8px">
                Sube un documento y lo analizaré automáticamente
            </p>
        </div>`;
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
    document.getElementById('processing-indicator').style.display = 'none';
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
    chatInput.addEventListener('input', function() { autoResize(this); });
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
// ========================================

const isMobile = window.innerWidth <= 768;

if (isMobile) {
    let touchStartY = 0;
    let touchEndY = 0;
    const capsule = document.getElementById('capsule-sources');
    if (capsule) {
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
            if (swipeDistance > 50 && !isExpanded) toggleCapsule('sources');
            else if (swipeDistance < -50 && isExpanded) toggleCapsule('sources');
        }
    }
    document.addEventListener('touchstart', (e) => {
        const capsuleSources = document.getElementById('capsule-sources');
        if (capsuleSources && capsuleSources.classList.contains('expanded')) {
            if (!capsuleSources.contains(e.target)) toggleCapsule('sources');
        }
    });
}

function scrollToBottom() {
    const messages = document.getElementById('chat-messages');
    if (messages && isMobile) {
        messages.scrollTo({ top: messages.scrollHeight, behavior: 'smooth' });
    }
}

const originalAgregarMensaje = agregarMensajeUsuario;
agregarMensajeUsuario = function(texto) {
    originalAgregarMensaje(texto);
    setTimeout(scrollToBottom, 100);
};

if (isMobile) {
    const chatInput = document.getElementById('chat-input');
    if (chatInput) {
        chatInput.addEventListener('focus', () => {
            setTimeout(() => {
                chatInput.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
            }, 300);
        });
        chatInput.addEventListener('focus', () => {
            const capsuleSources = document.getElementById('capsule-sources');
            if (capsuleSources && capsuleSources.classList.contains('expanded')) {
                toggleCapsule('sources');
            }
        });
    }
    let resizeTimeout;
    window.addEventListener('resize', () => {
        clearTimeout(resizeTimeout);
        resizeTimeout = setTimeout(() => {
            if (typeof lucide !== 'undefined') lucide.createIcons();
        }, 250);
    });
    document.body.addEventListener('touchmove', (e) => {
        if (e.target.closest('.chat-messages') ||
            e.target.closest('.sources-content') ||
            e.target.closest('.tools-content')) return;
        e.preventDefault();
    }, { passive: false });
}

function updateMobileBottomNav() {
    if (!isMobile) return;
    const capsule = document.getElementById('capsule-sources');
    if (!capsule) return;
    const collapsed = capsule.querySelector('.capsule-collapsed');
    if (!collapsed) return;
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
    if (typeof lucide !== 'undefined') lucide.createIcons();
}

if (isMobile) updateMobileBottomNav();

document.addEventListener('gesturestart', (e) => e.preventDefault());
document.addEventListener('gesturechange', (e) => e.preventDefault());
document.addEventListener('gestureend', (e) => e.preventDefault());

console.log('📱 Mobile enhancements loaded');

// ========================================
// POMODORO TIMER
// ========================================

let pomodoroInterval = null;
let pomodoroSeconds = 25 * 60;
let pomodoroMode = 'work';
let pomodoroSessions = 0;
let isPomodoroRunning = false;

function loadPomodoroStats() {
    const stats = localStorage.getItem('pomodoro_stats');
    if (stats) {
        const data = JSON.parse(stats);
        pomodoroSessions = data.sessions || 0;
        updatePomodoroStats();
    }
}

function savePomodoroStats() {
    localStorage.setItem('pomodoro_stats', JSON.stringify({
        sessions: pomodoroSessions,
        lastSession: new Date().toISOString()
    }));
}

function togglePomodoro() {
    const widget = document.getElementById('pomodoro-widget');
    if (!widget) createPomodoroWidget();
    else widget.classList.toggle('minimized');
}

function createPomodoroWidget() {
    const existing = document.getElementById('pomodoro-widget');
    if (existing) existing.remove();
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
    if (typeof lucide !== 'undefined') lucide.createIcons();
    loadPomodoroStats();
}

function startPomodoro() {
    if (isPomodoroRunning) return;
    isPomodoroRunning = true;
    document.getElementById('start-btn').style.display = 'none';
    document.getElementById('pause-btn').style.display = 'flex';
    pomodoroInterval = setInterval(() => {
        pomodoroSeconds--;
        updatePomodoroDisplay();
        if (pomodoroSeconds <= 0) finishPomodoro();
    }, 1000);
}

function pausePomodoro() {
    isPomodoroRunning = false;
    clearInterval(pomodoroInterval);
    document.getElementById('start-btn').style.display = 'flex';
    document.getElementById('pause-btn').style.display = 'none';
}

function resetPomodoro() {
    pausePomodoro();
    pomodoroSeconds = pomodoroMode === 'work' ? 25 * 60 : 5 * 60;
    updatePomodoroDisplay();
}

function finishPomodoro() {
    pausePomodoro();
    playPomodoroSound();
    if (pomodoroMode === 'work') {
        pomodoroSessions++;
        savePomodoroStats();
        updatePomodoroStats();
        pomodoroMode = 'break';
        pomodoroSeconds = 5 * 60;
        document.getElementById('pomodoro-mode').textContent = '☕ Tiempo de descanso';
        showPomodoroNotification('¡Sesión completada! 🎉', 'Toma un descanso de 5 minutos');
    } else {
        pomodoroMode = 'work';
        pomodoroSeconds = 25 * 60;
        document.getElementById('pomodoro-mode').textContent = '📚 Tiempo de estudio';
        showPomodoroNotification('¡Descanso terminado! 💪', 'Volvamos al trabajo');
    }
    updatePomodoroDisplay();
}

function updatePomodoroDisplay() {
    const minutes = Math.floor(pomodoroSeconds / 60);
    const seconds = pomodoroSeconds % 60;
    document.getElementById('pomodoro-time').textContent =
        `${minutes.toString().padStart(2, '0')}:${seconds.toString().padStart(2, '0')}`;
    const totalSeconds = pomodoroMode === 'work' ? 25 * 60 : 5 * 60;
    const progress = ((totalSeconds - pomodoroSeconds) / totalSeconds) * 100;
    const circumference = 2 * Math.PI * 45;
    const offset = circumference - (progress / 100) * circumference;
    document.getElementById('pomodoro-progress').style.strokeDashoffset = offset;
}

function updatePomodoroStats() {
    const el = document.getElementById('sessions-count');
    if (el) el.textContent = pomodoroSessions;
}

function playPomodoroSound() {
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

function showPomodoroNotification(title, message) {
    const notification = document.createElement('div');
    notification.className = 'pomodoro-notification';
    notification.innerHTML = `
        <div class="notification-content">
            <h4>${title}</h4>
            <p>${message}</p>
        </div>
    `;
    document.body.appendChild(notification);
    setTimeout(() => notification.classList.add('show'), 100);
    setTimeout(() => {
        notification.classList.remove('show');
        setTimeout(() => notification.remove(), 300);
    }, 3000);
    if ('Notification' in window && Notification.permission === 'granted') {
        new Notification(title, { body: message, icon: '/static/icon.png' });
    }
}

function minimizePomodoro() {
    document.getElementById('pomodoro-widget').classList.add('minimized');
}

function closePomodoro() {
    pausePomodoro();
    document.getElementById('pomodoro-widget').remove();
}

loadPomodoroStats();
console.log('⏱️ Pomodoro Timer loaded');

// ========================================
// MINDMAP VIEWER
// ========================================

let currentMindmap = null;

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
                    <i data-lucide="zoom-in" style="width:16px;height:16px;"></i> Zoom +
                </button>
                <button class="btn-mindmap" onclick="zoomOutMindmap()">
                    <i data-lucide="zoom-out" style="width:16px;height:16px;"></i> Zoom -
                </button>
                <button class="btn-mindmap" onclick="resetZoomMindmap()">
                    <i data-lucide="maximize" style="width:16px;height:16px;"></i> Reset
                </button>
                <button class="btn-mindmap primary" onclick="exportMindmap()">
                    <i data-lucide="download" style="width:16px;height:16px;"></i> Exportar
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
    renderMermaid(mermaidCode);
    if (typeof lucide !== 'undefined') lucide.createIcons();
}

async function renderMermaid(code) {
    const viewer = document.getElementById('mindmap-viewer');
    try {
        if (typeof mermaid === 'undefined') await loadMermaid();
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
                fontSize: '14px',
                fontFamily: '-apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif'
            },
            mindmap: { padding: 20, useMaxWidth: false }
        });
        const id = 'mermaid-' + Date.now();
        const { svg } = await mermaid.render(id, code);
        viewer.innerHTML = `<div class="mindmap-svg-container" id="svg-container">${svg}</div>`;
        makeMindmapDraggable();
    } catch (error) {
        console.error('Error rendering mermaid:', error);
        viewer.innerHTML = `
            <div class="mindmap-error">
                <i data-lucide="alert-circle" style="width:48px;height:48px;color:#ef4444;"></i>
                <h4>Error al renderizar mapa mental</h4>
                <p>${error.message}</p>
                <button class="btn-retry" onclick="renderMermaid(\`${code.replace(/`/g, '\\`')}\`)">Reintentar</button>
            </div>
        `;
        if (typeof lucide !== 'undefined') lucide.createIcons();
    }
}

function loadMermaid() {
    return new Promise((resolve, reject) => {
        if (typeof mermaid !== 'undefined') { resolve(); return; }
        const script = document.createElement('script');
        script.src = 'https://cdn.jsdelivr.net/npm/mermaid@10/dist/mermaid.min.js';
        script.onload = resolve;
        script.onerror = reject;
        document.head.appendChild(script);
    });
}

let currentZoom = 1;
function zoomInMindmap() { currentZoom += 0.2; applyZoom(); }
function zoomOutMindmap() { if (currentZoom > 0.4) { currentZoom -= 0.2; applyZoom(); } }
function resetZoomMindmap() { currentZoom = 1; applyZoom(); }
function applyZoom() {
    const container = document.getElementById('svg-container');
    if (container) container.style.transform = `scale(${currentZoom})`;
}

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
    viewer.addEventListener('mouseleave', () => { isDragging = false; viewer.style.cursor = 'grab'; });
    viewer.addEventListener('mouseup', () => { isDragging = false; viewer.style.cursor = 'grab'; });
    viewer.addEventListener('mousemove', (e) => {
        if (!isDragging) return;
        e.preventDefault();
        const x = e.pageX - viewer.offsetLeft;
        const y = e.pageY - viewer.offsetTop;
        viewer.scrollLeft = scrollLeft - (x - startX) * 2;
        viewer.scrollTop = scrollTop - (y - startY) * 2;
    });
}

async function exportMindmap() {
    try {
        const svg = document.querySelector('#svg-container svg');
        if (!svg) { alert('No hay mapa mental para exportar'); return; }
        const bbox = svg.getBBox();
        const width = bbox.width + 40;
        const height = bbox.height + 40;
        const canvas = document.createElement('canvas');
        canvas.width = width * 2;
        canvas.height = height * 2;
        const ctx = canvas.getContext('2d');
        ctx.fillStyle = document.body.classList.contains('dark') ? '#1a1a2e' : '#ffffff';
        ctx.fillRect(0, 0, canvas.width, canvas.height);
        const svgData = new XMLSerializer().serializeToString(svg);
        const svgBlob = new Blob([svgData], { type: 'image/svg+xml;charset=utf-8' });
        const url = URL.createObjectURL(svgBlob);
        const img = new Image();
        img.onload = function() {
            ctx.drawImage(img, 20, 20, width * 2 - 40, height * 2 - 40);
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
                if (fuente.content) contenido += fuente.content + '\n\n';
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
            headers: { 'Accept': 'application/json' },
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

// ========================================
// HIGHLIGHTS & NOTES SYSTEM
// ========================================

let highlights = [];
let currentSelection = null;

function loadHighlights() {
    const saved = localStorage.getItem('nux_highlights');
    if (saved) {
        try {
            highlights = JSON.parse(saved);
            console.log('✅ Highlights cargados:', highlights.length);
        } catch (e) {
            highlights = [];
        }
    }
}

function saveHighlights() {
    localStorage.setItem('nux_highlights', JSON.stringify(highlights));
    updateHighlightsBadge();
}

function handleTextSelection(e) {
    if (e.target.closest('.highlight-menu') || e.target.closest('.btn-highlights')) return;
    const selection = window.getSelection();
    const selectedText = selection.toString().trim();
    if (selectedText.length < 10) { hideHighlightMenu(); return; }
    const validContainer = selection.anchorNode?.parentElement?.closest('.chat-messages, .message-bubble, .resumen-content');
    if (!validContainer) { hideHighlightMenu(); return; }
    currentSelection = { text: selectedText };
    showHighlightMenu(e.pageX, e.pageY);
}

function showHighlightMenu(x, y) {
    hideHighlightMenu();
    const menu = document.createElement('div');
    menu.id = 'highlight-menu';
    menu.className = 'highlight-menu';
    menu.style.left = Math.min(x, window.innerWidth - 250) + 'px';
    menu.style.top = Math.min(y + 10, window.innerHeight - 100) + 'px';
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
    if (typeof lucide !== 'undefined') lucide.createIcons();
}

function hideHighlightMenu() {
    const menu = document.getElementById('highlight-menu');
    if (menu) menu.remove();
}

function addHighlight(color) {
    if (!currentSelection) return;
    highlights.push({
        id: Date.now(),
        text: currentSelection.text,
        color,
        note: '',
        timestamp: new Date().toISOString()
    });
    saveHighlights();
    hideHighlightMenu();
    window.getSelection().removeAllRanges();
    showHighlightFeedback(color);
    updateHighlightsPanel();
}

function addHighlightWithNote() {
    if (!currentSelection) return;
    hideHighlightMenu();
    const note = prompt('Añade una nota (opcional):');
    highlights.push({
        id: Date.now(),
        text: currentSelection.text,
        color: 'yellow',
        note: note || '',
        timestamp: new Date().toISOString()
    });
    saveHighlights();
    window.getSelection().removeAllRanges();
    showHighlightFeedback('yellow');
    updateHighlightsPanel();
}

function showHighlightFeedback(color) {
    const colorNames = { yellow: '🟡 Amarillo', green: '🟢 Verde', blue: '🔵 Azul', red: '🔴 Rojo' };
    const feedback = document.createElement('div');
    feedback.className = 'highlight-feedback';
    feedback.style.cssText = `
        position: fixed; top: 50%; left: 50%;
        transform: translate(-50%, -50%);
        background: var(--panel-bg); backdrop-filter: blur(12px);
        border: 2px solid var(--primary); border-radius: 12px;
        padding: 20px 40px; box-shadow: 0 8px 24px rgba(0,0,0,0.3);
        z-index: 10001; animation: fadeInOut 1.5s ease;
        font-weight: 600; display: flex; align-items: center; gap: 12px;
    `;
    feedback.innerHTML = `
        <i data-lucide="check-circle" style="width:24px;height:24px;color:var(--primary);"></i>
        <span>Highlight guardado: ${colorNames[color]}</span>
    `;
    document.body.appendChild(feedback);
    if (typeof lucide !== 'undefined') lucide.createIcons();
    setTimeout(() => feedback.remove(), 1500);
}

function toggleHighlightsPanel() {
    const panel = document.getElementById('highlights-panel');
    if (panel) panel.classList.toggle('open');
    else createHighlightsPanel();
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
    if (typeof lucide !== 'undefined') lucide.createIcons();
    updateHighlightsPanel();
}

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
        if (typeof lucide !== 'undefined') lucide.createIcons();
        return;
    }
    const sorted = [...highlights].sort((a, b) => new Date(b.timestamp) - new Date(a.timestamp));
    list.innerHTML = sorted.map(h => {
        const date = new Date(h.timestamp).toLocaleDateString('es-ES', {
            month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit'
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
    if (typeof lucide !== 'undefined') lucide.createIcons();
}

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

function deleteHighlight(id) {
    if (!confirm('¿Eliminar este highlight?')) return;
    highlights = highlights.filter(h => h.id !== id);
    saveHighlights();
    updateHighlightsPanel();
}

function exportHighlights() {
    if (highlights.length === 0) { alert('No tienes highlights para exportar'); return; }
    let text = '# MIS HIGHLIGHTS - NUX IA\n\n';
    text += `Exportado: ${new Date().toLocaleString('es-ES')}\n`;
    text += `Total: ${highlights.length} highlights\n\n---\n\n`;
    highlights.forEach((h, i) => {
        text += `## ${i + 1}. ${h.text}\n`;
        if (h.note) text += `**Nota:** ${h.note}\n`;
        text += `*Color: ${h.color}* | *Fecha: ${new Date(h.timestamp).toLocaleString('es-ES')}*\n\n`;
    });
    const blob = new Blob([text], { type: 'text/plain' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `nux-highlights-${Date.now()}.txt`;
    a.click();
    URL.revokeObjectURL(url);
}

function clearAllHighlights() {
    if (!confirm(`¿Borrar todos los ${highlights.length} highlights? Esta acción no se puede deshacer.`)) return;
    highlights = [];
    saveHighlights();
    updateHighlightsPanel();
}

function updateHighlightsBadge() {
    const badge = document.getElementById('highlights-badge');
    if (badge) {
        const count = highlights.length;
        badge.textContent = count;
        badge.style.display = count > 0 ? 'block' : 'none';
    }
}

document.addEventListener('DOMContentLoaded', () => {
    loadHighlights();
    document.addEventListener('mouseup', handleTextSelection);
    updateHighlightsBadge();
});

document.addEventListener('scroll', hideHighlightMenu, true);
document.addEventListener('mousedown', (e) => {
    if (!e.target.closest('.highlight-menu')) hideHighlightMenu();
});

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
