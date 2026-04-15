"use strict";

var Settings = (function () {
    // ---------------------------------------------------------------------------
    //    State
    var _currentSettings = null;
    var _pendingConfig = {};
    var _pendingEnv = {};
    var _restartRequired = false;
    var _restartPollingTimer = null;


    // ---------------------------------------------------------------------------
    //    Section metadata
    var _configSections = [
        {
            key: "scraper",
            label: "Scraper",
            desc: "Crawl limits and request behaviour",
            fields: [
                { key: "max_pages_per_job",            type: "number", desc: "Maximum pages per job (safety limit)" },
                { key: "max_crawl_depth",               type: "number", desc: "Maximum link-hop depth for infinite mode" },
                { key: "concurrent_pages_per_job",      type: "number", desc: "Pages scraped in parallel within one job" },
                { key: "blocked_domains",               type: "text",   desc: "Comma-separated domains to never scrape" },
                { key: "skip_extensions",               type: "text",   desc: "Comma-separated file extensions to skip" },
            ],
        },
        {
            key: "extraction",
            label: "Content Extraction",
            desc: "Text density and DOM filtering thresholds",
            fields: [
                { key: "min_text_density",  type: "number", desc: "Min ratio of text to tags (0.0–1.0)" },
                { key: "min_block_words",   type: "number", desc: "Min word count for a block to be kept" },
                { key: "strip_tags",        type: "text",   desc: "HTML tags always stripped from content" },
                { key: "strip_classes",     type: "text",   desc: "CSS classes stripped as non-content" },
            ],
        },
        {
            key: "code_detection",
            label: "Code Detection",
            desc: "Thresholds for identifying code blocks",
            fields: [
                { key: "min_symbol_density", type: "number", desc: "Symbol density to trigger code detection (0.0–1.0)" },
                { key: "code_symbols",       type: "text",   desc: "Symbols that count toward code density" },
            ],
        },
        {
            key: "classification",
            label: "AI Classification",
            desc: "Provider and confidence settings for automatic categorisation",
            fields: [
                { key: "provider",              type: "text",     desc: "Provider: none | bart | http_api" },
                { key: "confidence_threshold",  type: "number",   desc: "Min confidence to assign a label (0.0–1.0)" },
                { key: "max_words",             type: "number",   desc: "Words sent to the classifier per page" },
                { key: "candidate_labels",      type: "textarea", desc: "Comma-separated list of category labels for BART" },
                { key: "bart_inference_workers", type: "number",  desc: "Parallel BART inference threads (bart provider only)" },
                { key: "run_in_subprocess",     type: "text",     desc: "true = BART per-thread (parallel, more RAM) | false = BART in coordinator (sequential, 1x RAM)" },
                { key: "http_endpoint",         type: "text",     desc: "HTTP endpoint URL (http_api provider only)" },
                { key: "http_model",            type: "text",     desc: "Model name (http_api provider only)" },
                { key: "http_api_format",       type: "text",     desc: "API format: ollama | openai_chat (http_api only)" },
            ],
        },
        {
            key: "logging",
            label: "Logging",
            desc: "Log retention and size limits",
            fields: [
                { key: "log_retention_days",      type: "number", desc: "Days to keep log entries in the database" },
                { key: "max_log_entries_per_job", type: "number", desc: "Max log entries stored per job" },
            ],
        },
    ];

    var _envFields = [
        { key: "API_LOG_LEVEL",                          type: "text",   desc: "FastAPI log verbosity: debug | info | warning | error" },
        { key: "CELERY_WORKER_CONCURRENCY",              type: "number", desc: "Celery worker processes — requires docker compose up -d to apply" },
        { key: "SCRAPER_DEFAULT_TIMEOUT",                type: "number", desc: "HTTP request timeout in seconds" },
        { key: "SCRAPER_MAX_RETRIES",                    type: "number", desc: "Retry count for failed requests" },
        { key: "SCRAPER_RETRY_DELAY",                    type: "number", desc: "Seconds between retries (exponential backoff base)" },
        { key: "SCRAPER_USER_AGENT",                     type: "text",   desc: "HTTP User-Agent header sent with every request" },
        { key: "SCRAPER_MAX_CONCURRENT_REQUESTS",        type: "number", desc: "Max open HTTP sockets across all workers" },
        { key: "SCRAPER_RESPECT_ROBOTS_TXT",             type: "text",   desc: "Respect robots.txt: true | false" },
        { key: "SCRAPER_DEFAULT_DELAY_BETWEEN_REQUESTS", type: "number", desc: "Polite delay between requests in seconds" },
    ];


    // ---------------------------------------------------------------------------
    //    Initialization
    function init() {
        /* nothing until view activates */
    }

    function onActivate() {
        _loadAndRender();
    }


    // ---------------------------------------------------------------------------
    //    Data loading
    function _loadAndRender() {
        var container = Utils.el("view-settings");
        if (!container) { return; }

        container.innerHTML = "<p style='color:var(--text-muted);padding:20px'>Loading settings\u2026</p>";

        Api.getSettings()
            .then(function (data) {
                _currentSettings = data;
                _pendingConfig = {};
                _pendingEnv = {};
                _restartRequired = data.requires_restart || false;
                _render(container);
            })
            .catch(function (err) {
                container.innerHTML = (
                    "<p style='color:var(--accent-red);padding:20px'>" +
                    "Failed to load settings: " + err.message + "</p>"
                );
            });
    }

    // ---------------------------------------------------------------------------
    //    Rendering
    function _render(container) {
        Utils.clearElement(container);

        var header = Utils.createElement("div", { className: "view-header" }, [
            Utils.createElement("h2", {}, "Settings"),
            Utils.createElement("button", {
                className: "btn btn-secondary",
                onclick: function () { _loadAndRender(); },
                title: "Reload settings from disk",
            }, "\u21BB Reload"),
        ]);
        container.appendChild(header);

        var banner = _buildRestartBanner();
        banner.style.display = _restartRequired ? "flex" : "none";
        container.appendChild(banner);

        _configSections.forEach(function (section) {
            var sectionData = (_currentSettings.config || {})[section.key] || {};
            container.appendChild(_buildConfigSection(section, sectionData));
        });

        container.appendChild(_buildEnvSection());
        container.appendChild(_buildActionsBar());
    }

    
    // ---------------------------------------------------------------------------
    //    Restart banner (with Restart button)
    function _buildRestartBanner() {
        var dismissBtn = Utils.createElement("button", {
            className: "btn btn-secondary btn-small",
            onclick: function () {
                _restartRequired = false;
                var banner = Utils.el("settings-restart-banner");
                if (banner) { banner.style.display = "none"; }
            },
        }, "Dismiss");

        var restartBtn = Utils.createElement("button", {
            id: "btn-restart-containers",
            className: "btn btn-small",
            style: "background:var(--accent-orange);color:#000;font-weight:600",
            onclick: _confirmAndRestart,
        }, "\u21BA Restart Containers");

        var banner = Utils.createElement("div", {
            id: "settings-restart-banner",
            className: "restart-banner",
        }, [
            Utils.createElement("div", { className: "restart-banner-text" }, [
                Utils.createElement("span", { className: "restart-banner-icon" }, "\u26A0\uFE0F"),
                Utils.createElement("span", {}, (
                    ".env changes were saved. Restart containers to apply them " +
                    "(picks up .config + code changes too). " +
                    "Note: CELERY_WORKER_CONCURRENCY and connection settings " +
                    "require \u2018docker compose up -d\u2019 from the terminal."
                )),
            ]),
            Utils.createElement("div", { className: "restart-banner-actions" }, [
                restartBtn,
                dismissBtn,
            ]),
        ]);

        return banner;
    }

    function _showRestartBanner() {
        var banner = Utils.el("settings-restart-banner");
        if (banner) { banner.style.display = "flex"; }
    }


    // ---------------------------------------------------------------------------
    //    Restart flow
    function _confirmAndRestart() {
        if (!confirm(
            "Restart webscraper-api, webscraper-celery-worker, and webscraper-celery-beat?\n\n" +
            "The page will briefly go offline (~15 seconds) then reload automatically."
        )) {
            return;
        }

        var btn = Utils.el("btn-restart-containers");
        if (btn) {
            btn.disabled = true;
            btn.textContent = "Restarting\u2026";
        }

        _setStatus("Sending restart signal\u2026", "");

        Api.restartContainers()
            .then(function (data) {
                _setStatus(
                    "\u2714 " + data.message + " Waiting for containers to come back\u2026",
                    "success"
                );
                _startRestartPolling();
            })
            .catch(function (err) {
                _setStatus("\u2716 Restart failed: " + err.message, "error");
                if (btn) {
                    btn.disabled = false;
                    btn.textContent = "\u21BA Restart Containers";
                }
            });
    }

    function _startRestartPolling() {
        /* Clear any existing polling timer */
        if (_restartPollingTimer) {
            clearInterval(_restartPollingTimer);
        }

        var attempts = 0;
        var maxAttempts = 40; /* 40 × 3s = 2 minutes max */
        var wentOffline = false;

        _restartPollingTimer = setInterval(function () {
            attempts += 1;

            if (attempts > maxAttempts) {
                clearInterval(_restartPollingTimer);
                _setStatus(
                    "\u2716 Restart timed out. Containers may still be starting — " +
                    "try refreshing the page manually.",
                    "error"
                );
                return;
            }

            /* Poll health endpoint — lighter than system/status and works
               even without the docker socket available */
            Api.getHealth()
                .then(function (data) {
                    if (wentOffline && data.status === "healthy") {
                        /* API is back — reload the page */
                        clearInterval(_restartPollingTimer);
                        _setStatus("\u2714 Containers are back. Reloading\u2026", "success");
                        setTimeout(function () {
                            window.location.reload();
                        }, 1000);
                    }
                })
                .catch(function () {
                    /* API is offline — this is expected during restart */
                    wentOffline = true;
                    _setStatus(
                        "Waiting for containers\u2026 (offline — this is normal)",
                        ""
                    );
                });

        }, 3000); /* poll every 3 seconds */
    }


    // ---------------------------------------------------------------------------
    //    Config section builder
    function _buildConfigSection(sectionMeta, sectionData) {
        var wrapper = Utils.createElement("div", { className: "settings-section" });

        var header = Utils.createElement("div", { className: "settings-section-header" }, [
            Utils.createElement("div", { className: "settings-section-title" }, [
                Utils.createElement("h3", {}, sectionMeta.label),
                Utils.createElement("span", {
                    className: "settings-section-badge badge-hot",
                }, "Hot reload"),
            ]),
            Utils.createElement("span", { className: "settings-section-chevron" }, "\u25BC"),
        ]);

        header.addEventListener("click", function () {
            wrapper.classList.toggle("collapsed");
        });

        wrapper.appendChild(header);

        var body = Utils.createElement("div", { className: "settings-section-body" });

        sectionMeta.fields.forEach(function (field) {
            var currentValue = sectionData[field.key] !== undefined
                ? sectionData[field.key] : "";
            body.appendChild(_buildConfigRow(sectionMeta.key, field, currentValue));
        });

        /* Render any extra keys not in metadata */
        Object.keys(sectionData).forEach(function (key) {
            var known = sectionMeta.fields.some(function (f) { return f.key === key; });
            if (!known) {
                body.appendChild(_buildConfigRow(sectionMeta.key, {
                    key: key, type: "text", desc: "",
                }, sectionData[key]));
            }
        });

        wrapper.appendChild(body);
        return wrapper;
    }

    function _buildConfigRow(sectionKey, field, currentValue) {
        var inputEl = _buildInput(field.type, currentValue, function (newValue) {
            if (!_pendingConfig[sectionKey]) {
                _pendingConfig[sectionKey] = {};
            }
            if (newValue !== currentValue) {
                _pendingConfig[sectionKey][field.key] = newValue;
            } else {
                delete _pendingConfig[sectionKey][field.key];
                if (Object.keys(_pendingConfig[sectionKey]).length === 0) {
                    delete _pendingConfig[sectionKey];
                }
            }
        });

        return Utils.createElement("div", { className: "settings-row" }, [
            Utils.createElement("div", { className: "settings-label" }, [
                Utils.createElement("div", { className: "settings-label-name" }, field.key),
                Utils.createElement("div", { className: "settings-label-desc" }, field.desc || ""),
            ]),
            Utils.createElement("div", { className: "settings-input" }, [inputEl]),
        ]);
    }


    // ---------------------------------------------------------------------------
    //    Env section builder
    function _buildEnvSection() {
        var wrapper = Utils.createElement("div", { className: "settings-section" });

        var header = Utils.createElement("div", { className: "settings-section-header" }, [
            Utils.createElement("div", { className: "settings-section-title" }, [
                Utils.createElement("h3", {}, "Environment Variables"),
                Utils.createElement("span", {
                    className: "settings-section-badge badge-restart",
                }, "Restart required"),
            ]),
            Utils.createElement("span", { className: "settings-section-chevron" }, "\u25BC"),
        ]);

        header.addEventListener("click", function () {
            wrapper.classList.toggle("collapsed");
        });

        wrapper.appendChild(header);

        var body = Utils.createElement("div", { className: "settings-section-body" });

        body.appendChild(Utils.createElement("p", {
            style: "font-size:12px;color:var(--text-muted);margin-bottom:16px;line-height:1.5",
        }, (
            "Saved to .env on disk. Use the Restart Containers button above to apply. " +
            "Exception: CELERY_WORKER_CONCURRENCY and connection settings (host/port/credentials) " +
            "require \u2018docker compose up -d\u2019 from the terminal."
        )));

        var envData = _currentSettings.env || {};
        _envFields.forEach(function (field) {
            var currentValue = envData[field.key] !== undefined ? envData[field.key] : "";
            body.appendChild(_buildEnvRow(field, currentValue));
        });

        wrapper.appendChild(body);
        return wrapper;
    }

    function _buildEnvRow(field, currentValue) {
        var inputEl = _buildInput(field.type, currentValue, function (newValue) {
            if (newValue !== currentValue) {
                _pendingEnv[field.key] = newValue;
            } else {
                delete _pendingEnv[field.key];
            }
        });

        return Utils.createElement("div", { className: "settings-row" }, [
            Utils.createElement("div", { className: "settings-label" }, [
                Utils.createElement("div", { className: "settings-label-name" }, field.key),
                Utils.createElement("div", { className: "settings-label-desc" }, field.desc || ""),
            ]),
            Utils.createElement("div", { className: "settings-input" }, [inputEl]),
        ]);
    }


    // ---------------------------------------------------------------------------
    //    Generic input builder
    function _buildInput(type, currentValue, onChange) {
        var el;

        if (type === "textarea") {
            el = document.createElement("textarea");
            el.value = currentValue;
            el.rows = 3;
            el.addEventListener("input", function () { onChange(el.value); });
            return el;
        }

        el = document.createElement("input");
        el.type = "text";
        el.value = currentValue;
        el.addEventListener("input", function () { onChange(el.value); });
        return el;
    }


    // ---------------------------------------------------------------------------
    //    Actions bar
    function _buildActionsBar() {
        var statusEl = Utils.createElement("div", {
            id: "settings-save-status",
            className: "settings-save-status",
        }, "");

        var saveBtn = Utils.createElement("button", {
            id: "btn-settings-save",
            className: "btn btn-primary",
            onclick: _saveSettings,
        }, "Apply Changes");

        var resetBtn = Utils.createElement("button", {
            className: "btn btn-secondary",
            onclick: _loadAndRender,
        }, "Reset");

        return Utils.createElement("div", { className: "settings-actions" }, [
            statusEl,
            Utils.createElement("div", { className: "settings-actions-right" }, [
                resetBtn, saveBtn,
            ]),
        ]);
    }


    // ---------------------------------------------------------------------------
    //    Save logic
    function _saveSettings() {
        var hasConfig = Object.keys(_pendingConfig).length > 0;
        var hasEnv = Object.keys(_pendingEnv).length > 0;

        if (!hasConfig && !hasEnv) {
            _setStatus("No changes to save.", "");
            return;
        }

        var saveBtn = Utils.el("btn-settings-save");
        if (saveBtn) {
            saveBtn.disabled = true;
            saveBtn.textContent = "Saving\u2026";
        }

        _setStatus("Saving\u2026", "");

        var payload = {};
        if (hasConfig) { payload.config = _pendingConfig; }
        if (hasEnv)    { payload.env = _pendingEnv; }

        Api.updateSettings(payload)
            .then(function (response) {
                _pendingConfig = {};
                _pendingEnv = {};

                if (response.requires_restart) {
                    _restartRequired = true;
                    _showRestartBanner();
                    _setStatus(
                        "\u2714 Saved. Use \u2018Restart Containers\u2019 to apply.",
                        "success"
                    );
                } else {
                    _setStatus("\u2714 " + response.message, "success");
                }

                Api.getSettings().then(function (fresh) {
                    _currentSettings = fresh;
                });
            })
            .catch(function (err) {
                _setStatus("\u2716 Error: " + err.message, "error");
            })
            .finally(function () {
                if (saveBtn) {
                    saveBtn.disabled = false;
                    saveBtn.textContent = "Apply Changes";
                }
            });
    }

    function _setStatus(message, cls) {
        var el = Utils.el("settings-save-status");
        if (!el) { return; }
        el.textContent = message;
        el.className = "settings-save-status" + (cls ? " " + cls : "");
    }


    // ---------------------------------------------------------------------------
    //    Public API
    return {
        init: init,
        onActivate: onActivate,
    };

}());
