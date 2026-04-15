"use strict";

var JobConfig = (function () {

    var _selectedMode = "single";
    var _jsMode = "auto";          /* auto | always | never */
    var _urlRules = [];
    var _categories = [];
    var _credentials = [];


    // ---------------------------------------------------------------------------
    //    Initialization
    function init() {
        _renderForm();
    }

    function onActivate() {
        _loadDropdownData();
    }


    // ---------------------------------------------------------------------------
    //    Form Rendering
    function _renderForm() {
        var container = Utils.el("view-job-config");
        if (!container) { return; }

        Utils.clearElement(container);

        container.appendChild(Utils.createElement("div", { className: "view-header" }, [
            Utils.createElement("h2", {}, "Create New Job"),
        ]));

        var form = Utils.createElement("div", { className: "job-config-form" });

        /* --- Job Details --- */
        form.appendChild(_createCard("Job Details", [
            _createFormGroup("job-name", "Job Name", "input", {
                placeholder: "e.g., Daily Blog Scrape",
            }),
            _createFormGroup("job-url", "Start URL", "input", {
                placeholder: "https://example.com",
                type: "url",
            }),
        ]));

        /* --- Crawl Mode --- */
        var modeCard = _createCard("Crawl Mode", []);
        var modeSelector = Utils.createElement("div", { className: "mode-selector" });

        [
            { value: "single",     title: "Single",     desc: "Scrape one URL" },
            { value: "rule_based", title: "Rule-Based",  desc: "Follow matching links" },
            { value: "infinite",   title: "Infinite",    desc: "Follow all same-domain links" },
            { value: "category",   title: "Category",    desc: "Match category patterns" },
        ].forEach(function (mode) {
            var option = Utils.createElement("div", {
                className: "mode-option" + (mode.value === _selectedMode ? " selected" : ""),
                dataset: { mode: mode.value },
                onClick: function () { _selectMode(mode.value); },
            }, [
                Utils.createElement("div", { className: "mode-option-title" }, mode.title),
                Utils.createElement("div", { className: "mode-option-desc" },  mode.desc),
            ]);
            modeSelector.appendChild(option);
        });

        modeCard.appendChild(modeSelector);
        form.appendChild(modeCard);

        /* --- URL Rules (rule_based / category modes) --- */
        var rulesCard = Utils.createElement("div", {
            id: "rules-card",
            className: "card" + (_selectedMode === "rule_based" || _selectedMode === "category" ? "" : " hidden"),
        });
        rulesCard.appendChild(Utils.createElement("div", { className: "card-header" }, [
            Utils.createElement("h3", {}, "URL Rules"),
            Utils.createElement("button", {
                className: "btn btn-small btn-secondary",
                textContent: "+ Add Rule",
                onClick: function () { _addRule(); },
            }),
        ]));
        rulesCard.appendChild(Utils.createElement("div", { id: "rules-list", className: "rules-list" }));
        form.appendChild(rulesCard);

        /* --- Data Targets --- */
        var targetsCard = _createCard("Data Targets", []);
        var targetsGrid = Utils.createElement("div", { className: "checkbox-group targets-grid" });

        [
            { value: "text",    label: "Text Content",  checked: true  },
            { value: "headers", label: "Page Headers",  checked: false },
            { value: "footers", label: "Page Footers",  checked: false },
            { value: "ads",     label: "Advertisements", checked: false },
        ].forEach(function (target) {
            var checkbox = Utils.createElement("input", {
                type: "checkbox",
                value: target.value,
                className: "target-checkbox",
            });
            if (target.checked) { checkbox.checked = true; }

            var label = Utils.createElement("label", { className: "checkbox-label" }, [
                checkbox,
                document.createTextNode(target.label),
            ]);
            targetsGrid.appendChild(label);
        });

        targetsCard.appendChild(targetsGrid);
        form.appendChild(targetsCard);

        /* --- JavaScript Rendering --- */
        form.appendChild(_buildJsModeCard());

        /* --- Assignment --- */
        var assignCard = _createCard("Assignment (Optional)", []);
        var assignRow = Utils.createElement("div", { className: "form-row" });

        var catGroup = Utils.createElement("div", { className: "form-group" });
        catGroup.appendChild(Utils.createElement("label", { for: "job-category" }, "Category"));
        var catSelect = Utils.createElement("select", { id: "job-category", className: "form-select" });
        catSelect.appendChild(Utils.createElement("option", { value: "" }, "None"));
        catGroup.appendChild(catSelect);
        assignRow.appendChild(catGroup);

        var credGroup = Utils.createElement("div", { className: "form-group" });
        credGroup.appendChild(Utils.createElement("label", { for: "job-credential" }, "Credential"));
        var credSelect = Utils.createElement("select", { id: "job-credential", className: "form-select" });
        credSelect.appendChild(Utils.createElement("option", { value: "" }, "None"));
        credGroup.appendChild(credSelect);
        assignRow.appendChild(credGroup);

        assignCard.appendChild(assignRow);
        form.appendChild(assignCard);

        /* --- Submit --- */
        form.appendChild(Utils.createElement("div", { className: "form-submit" }, [
            Utils.createElement("button", {
                className: "btn btn-secondary",
                textContent: "Reset",
                onClick: function () { _resetForm(); },
            }),
            Utils.createElement("button", {
                id: "btn-create-job",
                className: "btn btn-primary",
                textContent: "Create Job",
                onClick: function () { _submitJob(); },
            }),
        ]));

        container.appendChild(form);
    }


    // ---------------------------------------------------------------------------
    //    JS Mode Card
    function _buildJsModeCard() {
        var card = _createCard("JavaScript Rendering", []);

        var desc = Utils.createElement("p", {
            style: "font-size:12px;color:var(--text-muted);margin-bottom:14px;line-height:1.5",
        }, (
            "Controls whether Playwright (headless Chromium) is used to render " +
            "JavaScript-heavy pages. Auto detects SPA frameworks and empty pages automatically."
        ));
        card.appendChild(desc);

        var group = Utils.createElement("div", { className: "mode-selector" });

        [
            {
                value: "auto",
                title: "\uD83E\uDD16 Auto",
                desc: "Detect automatically (recommended)",
            },
            {
                value: "always",
                title: "\uD83C\uDF10 Always",
                desc: "Always use Playwright",
            },
            {
                value: "never",
                title: "\u26A1 Never",
                desc: "Plain HTTP only (fastest)",
            },
        ].forEach(function (opt) {
            var option = Utils.createElement("div", {
                className: "mode-option" + (opt.value === _jsMode ? " selected" : ""),
                dataset: { jsmode: opt.value },
                onClick: function () { _selectJsMode(opt.value); },
            }, [
                Utils.createElement("div", { className: "mode-option-title" }, opt.title),
                Utils.createElement("div", { className: "mode-option-desc" },  opt.desc),
            ]);
            group.appendChild(option);
        });

        card.appendChild(group);
        return card;
    }

    function _selectJsMode(mode) {
        _jsMode = mode;

        Utils.qsa("[data-jsmode]").forEach(function (el) {
            if (el.dataset.jsmode === mode) {
                el.classList.add("selected");
            } else {
                el.classList.remove("selected");
            }
        });
    }


    // ---------------------------------------------------------------------------
    //    Crawl Mode Selection
    function _selectMode(mode) {
        _selectedMode = mode;

        Utils.qsa(".mode-option[data-mode]").forEach(function (el) {
            if (el.dataset.mode === mode) {
                el.classList.add("selected");
            } else {
                el.classList.remove("selected");
            }
        });

        var rulesCard = Utils.el("rules-card");
        if (rulesCard) {
            if (mode === "rule_based" || mode === "category") {
                rulesCard.classList.remove("hidden");
            } else {
                rulesCard.classList.add("hidden");
            }
        }
    }


    // ---------------------------------------------------------------------------
    //    URL Rules Builder
    function _addRule() {
        _urlRules.push({ type: "contains", pattern: "" });
        _renderRules();
    }

    function _removeRule(index) {
        _urlRules.splice(index, 1);
        _renderRules();
    }

    function _renderRules() {
        var container = Utils.el("rules-list");
        if (!container) { return; }

        Utils.clearElement(container);

        if (_urlRules.length === 0) {
            container.appendChild(Utils.createElement("p", {
                className: "text-muted",
                style: "font-size:13px",
                textContent: "No rules added. Click \"+ Add Rule\" above.",
            }));
            return;
        }

        _urlRules.forEach(function (rule, index) {
            var row = Utils.createElement("div", { className: "rule-row" });

            var typeSelect = Utils.createElement("select", { className: "form-select" });
            [
                { value: "contains",    label: "Contains" },
                { value: "starts_with", label: "Starts With" },
                { value: "ends_with",   label: "Ends With" },
                { value: "regex",       label: "Regex" },
                { value: "domain",      label: "Domain" },
            ].forEach(function (rt) {
                var opt = Utils.createElement("option", { value: rt.value }, rt.label);
                if (rt.value === rule.type) { opt.selected = true; }
                typeSelect.appendChild(opt);
            });
            typeSelect.addEventListener("change", function () {
                _urlRules[index].type = typeSelect.value;
            });
            row.appendChild(typeSelect);

            var patternInput = Utils.createElement("input", {
                type: "text",
                className: "form-input",
                placeholder: "e.g., /blog/ or example.com",
                value: rule.pattern,
            });
            patternInput.addEventListener("input", function () {
                _urlRules[index].pattern = patternInput.value;
            });
            row.appendChild(patternInput);

            row.appendChild(Utils.createElement("button", {
                className: "btn btn-small btn-icon",
                textContent: "\u00D7",
                title: "Remove rule",
                onClick: function () { _removeRule(index); },
            }));

            container.appendChild(row);
        });
    }


    // ---------------------------------------------------------------------------
    //    Dropdown Data Loading
    function _loadDropdownData() {
        Api.listCategories()
            .then(function (data) {
                _categories = data.categories || [];
                _populateCategoryDropdown();
            })
            .catch(function () {});

        Api.listCredentials()
            .then(function (data) {
                _credentials = data.credentials || [];
                _populateCredentialDropdown();
            })
            .catch(function () {});
    }

    function _populateCategoryDropdown() {
        var select = Utils.el("job-category");
        if (!select) { return; }
        while (select.options.length > 1) { select.remove(1); }
        _categories.forEach(function (cat) {
            select.appendChild(Utils.createElement("option", { value: cat.id }, cat.name));
        });
    }

    function _populateCredentialDropdown() {
        var select = Utils.el("job-credential");
        if (!select) { return; }
        while (select.options.length > 1) { select.remove(1); }
        _credentials.forEach(function (cred) {
            select.appendChild(Utils.createElement("option", {
                value: cred.id,
            }, cred.domain + " (" + cred.username + ")"));
        });
    }


    // ---------------------------------------------------------------------------
    //    Form Submission
    function _submitJob() {
        var name = _getInputValue("job-name");
        var startUrl = _getInputValue("job-url");

        if (!name.trim()) {
            Utils.showToast("Please enter a job name", "warning");
            return;
        }
        if (!startUrl.trim()) {
            Utils.showToast("Please enter a start URL", "warning");
            return;
        }

        var dataTargets = [];
        Utils.qsa(".target-checkbox").forEach(function (cb) {
            if (cb.checked) { dataTargets.push(cb.value); }
        });
        if (dataTargets.length === 0) { dataTargets = ["text"]; }

        var jobData = {
            name:        name.trim(),
            start_url:   startUrl.trim(),
            crawl_mode:  _selectedMode,
            data_targets: dataTargets,
            js_mode:     _jsMode,
        };

        if ((_selectedMode === "rule_based" || _selectedMode === "category") &&
            _urlRules.length > 0) {
            var validRules = _urlRules.filter(function (r) {
                return r.pattern.trim() !== "";
            });
            if (validRules.length > 0) { jobData.url_rules = validRules; }
        }

        var categoryId = _getSelectValue("job-category");
        if (categoryId) { jobData.category_id = categoryId; }

        var credentialId = _getSelectValue("job-credential");
        if (credentialId) { jobData.credential_id = credentialId; }

        var submitBtn = Utils.el("btn-create-job");
        if (submitBtn) {
            submitBtn.disabled = true;
            submitBtn.textContent = "Creating\u2026";
        }

        Api.createJob(jobData)
            .then(function (job) {
                Utils.showToast("Job \"" + job.name + "\" created successfully!", "success");
                _resetForm();
                App.navigateTo("dashboard");
            })
            .catch(function (err) {
                Utils.showToast("Failed to create job: " + err.message, "error");
            })
            .finally(function () {
                if (submitBtn) {
                    submitBtn.disabled = false;
                    submitBtn.textContent = "Create Job";
                }
            });
    }

    function _resetForm() {
        _selectedMode = "single";
        _jsMode = "auto";
        _urlRules = [];

        var nameInput = Utils.el("job-name");
        if (nameInput) { nameInput.value = ""; }

        var urlInput = Utils.el("job-url");
        if (urlInput) { urlInput.value = ""; }

        Utils.qsa(".target-checkbox").forEach(function (cb) {
            cb.checked = cb.value === "text";
        });

        var catSelect = Utils.el("job-category");
        if (catSelect) { catSelect.value = ""; }

        var credSelect = Utils.el("job-credential");
        if (credSelect) { credSelect.value = ""; }

        _selectMode("single");
        _selectJsMode("auto");
        _renderRules();
    }


    // ---------------------------------------------------------------------------
    //    Helpers
    function _createCard(title, children) {
        var card = Utils.createElement("div", { className: "card" });
        if (title) {
            card.appendChild(Utils.createElement("div", { className: "card-header" }, [
                Utils.createElement("h3", {}, title),
            ]));
        }
        if (children) {
            children.forEach(function (child) { card.appendChild(child); });
        }
        return card;
    }

    function _createFormGroup(id, label, type, attrs) {
        var group = Utils.createElement("div", { className: "form-group" });
        group.appendChild(Utils.createElement("label", { for: id }, label));

        var inputAttrs = { id: id, className: "form-input" };
        if (attrs) {
            Object.keys(attrs).forEach(function (key) {
                inputAttrs[key] = attrs[key];
            });
        }

        if (type === "textarea") {
            group.appendChild(Utils.createElement("textarea", inputAttrs));
        } else {
            inputAttrs.type = (attrs && attrs.type) ? attrs.type : "text";
            group.appendChild(Utils.createElement("input", inputAttrs));
        }
        return group;
    }

    function _getInputValue(id) {
        var el = Utils.el(id);
        return el ? el.value : "";
    }

    function _getSelectValue(id) {
        var el = Utils.el(id);
        return (el && el.value) ? el.value : null;
    }


    // ---------------------------------------------------------------------------
    //    Public API
    return {
        init: init,
        onActivate: onActivate,
    };

})();
