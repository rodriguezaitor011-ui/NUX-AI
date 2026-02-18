// ============================================
// NUX AI - i18n SYSTEM
// Sistema de internacionalización multi-idioma
// ============================================

class I18n {
    constructor() {
        this.currentLang = 'es'; // Default
        this.translations = {};
        this.availableLanguages = ['es', 'en', 'fr', 'pt', 'de'];
        this.flagEmojis = {
            'es': '🇪🇸',
            'en': '🇬🇧',
            'fr': '🇫🇷',
            'pt': '🇵🇹',
            'de': '🇩🇪'
        };
        this.languageNames = {
            'es': 'Español',
            'en': 'English',
            'fr': 'Français',
            'pt': 'Português',
            'de': 'Deutsch'
        };
    }

    async init() {
        console.log('🌍 Iniciando sistema i18n...');
        
        // 1. Detectar idioma preferido
        const savedLang = localStorage.getItem('nux_language');
        const browserLang = this.detectBrowserLanguage();
        
        this.currentLang = savedLang || browserLang || 'es';
        
        console.log(`📍 Idioma detectado: ${this.currentLang}`);
        
        // 2. Cargar traducciones
        await this.loadTranslations(this.currentLang);
        
        // 3. Aplicar traducciones
        this.applyTranslations();
        
        // 4. Crear selector de idioma
        this.createLanguageSelector();
        
        // 5. Update HTML lang attribute
        document.documentElement.lang = this.currentLang;
        
        console.log('✅ Sistema i18n inicializado');
    }

    detectBrowserLanguage() {
        const browserLang = navigator.language || navigator.userLanguage;
        const langCode = browserLang.split('-')[0]; // 'es-ES' → 'es'
        
        // Verificar si el idioma está disponible
        if (this.availableLanguages.includes(langCode)) {
            return langCode;
        }
        
        return 'en'; // Fallback a inglés
    }

    async loadTranslations(lang) {
        try {
            const response = await fetch(`/static/translations/${lang}.json`);
            
            if (!response.ok) {
                throw new Error(`Failed to load ${lang}.json`);
            }
            
            this.translations = await response.json();
            console.log(`✅ Traducciones cargadas: ${lang}`);
            
        } catch (error) {
            console.error(`❌ Error cargando traducciones ${lang}:`, error);
            
            // Fallback a español
            if (lang !== 'es') {
                console.log('⚠️ Intentando cargar español como fallback...');
                await this.loadTranslations('es');
            }
        }
    }

    t(key) {
        // Navegar por el objeto de traducciones usando el key
        // Ejemplo: t('app.upload.title') → translations.app.upload.title
        
        const keys = key.split('.');
        let value = this.translations;
        
        for (const k of keys) {
            if (value && typeof value === 'object') {
                value = value[k];
            } else {
                console.warn(`⚠️ Translation key not found: ${key}`);
                return key; // Devolver el key si no se encuentra
            }
        }
        
        return value || key;
    }

    applyTranslations() {
        console.log('🔄 Aplicando traducciones al DOM...');
        
        // Buscar todos los elementos con atributo data-i18n
        const elements = document.querySelectorAll('[data-i18n]');
        
        elements.forEach(element => {
            const key = element.getAttribute('data-i18n');
            const translation = this.t(key);
            
            // Determinar si es texto o placeholder
            if (element.tagName === 'INPUT' || element.tagName === 'TEXTAREA') {
                element.placeholder = translation;
            } else {
                element.textContent = translation;
            }
        });
        
        // Actualizar meta tags
        this.updateMetaTags();
        
        console.log(`✅ Traducciones aplicadas (${elements.length} elementos)`);
    }

    updateMetaTags() {
        // Title
        document.title = this.t('meta.title');
        
        // Description
        const metaDesc = document.querySelector('meta[name="description"]');
        if (metaDesc) {
            metaDesc.content = this.t('meta.description');
        }
    }

    async changeLanguage(newLang) {
        if (!this.availableLanguages.includes(newLang)) {
            console.error(`❌ Idioma no disponible: ${newLang}`);
            return;
        }
        
        console.log(`🔄 Cambiando idioma a: ${newLang}`);
        
        this.currentLang = newLang;
        
        // Guardar preferencia
        localStorage.setItem('nux_language', newLang);
        
        // Cargar nuevas traducciones
        await this.loadTranslations(newLang);
        
        // Aplicar
        this.applyTranslations();
        
        // Update HTML lang
        document.documentElement.lang = newLang;
        
        // Update selector UI
        this.updateLanguageSelector();
        
        // Trigger custom event para que otros componentes reaccionen
        window.dispatchEvent(new CustomEvent('languageChanged', { 
            detail: { language: newLang } 
        }));
        
        console.log(`✅ Idioma cambiado a: ${newLang}`);
    }

    createLanguageSelector() {
        // Crear selector en el header
        const header = document.querySelector('header nav') || document.querySelector('nav');
        
        if (!header) {
            console.warn('⚠️ No se encontró header para añadir selector de idioma');
            return;
        }
        
        const selectorHTML = `
            <div class="language-selector" id="language-selector">
                <button class="lang-btn" id="lang-btn" aria-label="Select language">
                    <span class="lang-flag">${this.flagEmojis[this.currentLang]}</span>
                    <span class="lang-code">${this.currentLang.toUpperCase()}</span>
                    <svg width="12" height="12" viewBox="0 0 12 12" fill="none">
                        <path d="M2 4L6 8L10 4" stroke="currentColor" stroke-width="2" stroke-linecap="round"/>
                    </svg>
                </button>
                <div class="lang-dropdown" id="lang-dropdown">
                    ${this.availableLanguages.map(lang => `
                        <button class="lang-option ${lang === this.currentLang ? 'active' : ''}" 
                                data-lang="${lang}"
                                aria-label="${this.languageNames[lang]}">
                            <span class="lang-flag">${this.flagEmojis[lang]}</span>
                            <span class="lang-name">${this.languageNames[lang]}</span>
                            ${lang === this.currentLang ? '<span class="check">✓</span>' : ''}
                        </button>
                    `).join('')}
                </div>
            </div>
        `;
        
        // Insertar al final del nav
        header.insertAdjacentHTML('beforeend', selectorHTML);
        
        // Event listeners
        this.setupLanguageSelectorEvents();
    }

    setupLanguageSelectorEvents() {
        const btn = document.getElementById('lang-btn');
        const dropdown = document.getElementById('lang-dropdown');
        const options = document.querySelectorAll('.lang-option');
        
        if (!btn || !dropdown) return;
        
        // Toggle dropdown
        btn.addEventListener('click', (e) => {
            e.stopPropagation();
            dropdown.classList.toggle('show');
        });
        
        // Close dropdown al hacer click fuera
        document.addEventListener('click', () => {
            dropdown.classList.remove('show');
        });
        
        // Cambiar idioma
        options.forEach(option => {
            option.addEventListener('click', async (e) => {
                e.stopPropagation();
                const newLang = option.dataset.lang;
                
                if (newLang !== this.currentLang) {
                    await this.changeLanguage(newLang);
                }
                
                dropdown.classList.remove('show');
            });
        });
    }

    updateLanguageSelector() {
        const btn = document.getElementById('lang-btn');
        const options = document.querySelectorAll('.lang-option');
        
        if (btn) {
            btn.querySelector('.lang-flag').textContent = this.flagEmojis[this.currentLang];
            btn.querySelector('.lang-code').textContent = this.currentLang.toUpperCase();
        }
        
        options.forEach(option => {
            const lang = option.dataset.lang;
            const isActive = lang === this.currentLang;
            
            option.classList.toggle('active', isActive);
            
            const check = option.querySelector('.check');
            if (check) {
                check.remove();
            }
            
            if (isActive) {
                option.insertAdjacentHTML('beforeend', '<span class="check">✓</span>');
            }
        });
    }

    // Helper para traducir dinámicamente en JS
    translate(key) {
        return this.t(key);
    }

    // Helper para obtener idioma actual
    getCurrentLanguage() {
        return this.currentLang;
    }

    // Helper para verificar si un idioma está disponible
    isLanguageAvailable(lang) {
        return this.availableLanguages.includes(lang);
    }
}

// Instancia global
const i18n = new I18n();

// Auto-inicializar cuando el DOM esté listo
if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', () => i18n.init());
} else {
    i18n.init();
}

// Exportar para uso global
window.i18n = i18n;
