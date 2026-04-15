"use strict";

var Categories = (function () {

    var _categories = [];
    var _editingId = null;
    var _formKeywords = [];
    var _formPatterns = [];

    
    // ---------------------------------------------------------------------------
    //    Initialization
    function init() {
        _renderLayout();
    }

    function onActivate() {
        _loadCategories();
    }


    // ---------------------------------------------------------------------------
    //    Layout
    function _renderLayout() {
        var container = Utils.el("view-categories");
        if (!container) {
            return;
        }

        Utils.clearElement(container);

        // Header
        container.appendChild(Utils.createElement("div", { className: "categories-header" }, [
            Utils.createElement("h2", {}, "Categories Manager"),
            Utils.createElement("button", {
                className: "btn btn-primary",
                textContent: "+ Add Category",
                onClick: function () {
                    _showForm(null);
                },
            }),
        ]));

        // Category list
        container.appendChild(Utils.createElement("div", { id: "categories-list" }));

        // Form (hidden by default)
        container.appendChild(Utils.createElement("div", {
            id: "category-form-container",
            className: "hidden",
        }));
    }


    // ---------------------------------------------------------------------------
    //    Data Loading
    function _loadCategories() {
        Api.listCategories()
            .then(function (data) {
                _categories = data.categories || [];
                _renderList();
            })
            .catch(function (err) {
                Utils.showToast("Failed to load categories: " + err.message, "error");
            });
    }


    // ---------------------------------------------------------------------------
    //    List Rendering
    function _renderList() {
        var container = Utils.el("categories-list");
        if (!container) {
            return;
        }

        Utils.clearElement(container);

        if (_categories.length === 0) {
            container.appendChild(Utils.createElement("div", {
                className: "card",
                style: "text-align: center; padding: 40px;",
            }, [
                Utils.createElement("p", {
                    className: "text-muted",
                    textContent: "No categories created yet. Add one to classify scraped content.",
                }),
            ]));
            return;
        }

        _categories.forEach(function (cat) {
            var card = Utils.createElement("div", { className: "category-card" });

            // Header row
            var headerRow = Utils.createElement("div", { className: "category-card-header" });

            var nameGroup = Utils.createElement("div", { className: "flex items-center gap-8" }, [
                Utils.createElement("span", { className: "category-name", textContent: cat.name }),
                Utils.createElement("span", {
                    className: "category-status " + (cat.is_active ? "active" : "inactive"),
                    textContent: cat.is_active ? "Active" : "Inactive",
                }),
            ]);
            headerRow.appendChild(nameGroup);

            var actions = Utils.createElement("div", { className: "btn-group" }, [
                Utils.createElement("button", {
                    className: "btn btn-small btn-secondary",
                    textContent: "Edit",
                    onClick: function () {
                        _showForm(cat);
                    },
                }),
                Utils.createElement("button", {
                    className: "btn btn-small btn-danger",
                    textContent: "Delete",
                    onClick: function () {
                        _deleteCategory(cat.id, cat.name);
                    },
                }),
            ]);
            headerRow.appendChild(actions);
            card.appendChild(headerRow);

            // Description
            if (cat.description) {
                card.appendChild(Utils.createElement("p", {
                    className: "category-description",
                    textContent: cat.description,
                }));
            }

            // Keywords
            var keywords = cat.keywords || [];
            if (keywords.length > 0) {
                var tagsDiv = Utils.createElement("div", { className: "keyword-tags" });
                keywords.forEach(function (kw) {
                    tagsDiv.appendChild(Utils.createElement("span", {
                        className: "keyword-tag",
                        textContent: kw,
                    }));
                });
                card.appendChild(tagsDiv);
            }

            // URL Patterns
            var patterns = cat.url_patterns || [];
            if (patterns.length > 0) {
                var patternsDiv = Utils.createElement("div", { className: "url-patterns" });

                patterns.forEach(function (p) {
                    patternsDiv.appendChild(Utils.createElement("div", { className: "url-pattern-item" }, [
                        Utils.createElement("span", {
                            className: "url-pattern-type",
                            textContent: p.type || "contains",
                        }),
                        Utils.createElement("span", {
                            className: "url-pattern-value",
                            textContent: p.pattern || "",
                        }),
                    ]));
                });

                card.appendChild(patternsDiv);
            }

            container.appendChild(card);
        });
    }


    // ---------------------------------------------------------------------------
    //    Form
    function _showForm(category) {
        _editingId = category ? category.id : null;
        _formKeywords = category && category.keywords ? category.keywords.slice() : [];
        _formPatterns = category && category.url_patterns ? category.url_patterns.map(function (p) { return { type: p.type, pattern: p.pattern }; }) : [];

        var formContainer = Utils.el("category-form-container");
        if (!formContainer) {
            return;
        }

        Utils.clearElement(formContainer);
        formContainer.classList.remove("hidden");

        var isEdit = category !== null;
        var title = isEdit ? "Edit Category" : "Add Category";

        var form = Utils.createElement("div", { className: "card category-form mt-24" });

        // Header
        form.appendChild(Utils.createElement("div", { className: "card-header" }, [
            Utils.createElement("h3", {}, title),
            Utils.createElement("button", {
                className: "btn btn-small btn-secondary",
                textContent: "Cancel",
                onClick: function () {
                    _hideForm();
                },
            }),
        ]));

        // Name
        var nameGroup = Utils.createElement("div", { className: "form-group" });
        nameGroup.appendChild(Utils.createElement("label", {}, "Category Name"));
        var nameInput = Utils.createElement("input", {
            id: "cat-name",
            type: "text",
            className: "form-input",
            placeholder: "e.g., Technology",
        });
        if (isEdit) {
            nameInput.value = category.name;
        }
        nameGroup.appendChild(nameInput);
        form.appendChild(nameGroup);

        // Description
        var descGroup = Utils.createElement("div", { className: "form-group" });
        descGroup.appendChild(Utils.createElement("label", {}, "Description (optional)"));
        var descInput = Utils.createElement("textarea", {
            id: "cat-description",
            className: "form-textarea",
            placeholder: "Brief description of this category...",
        });
        if (isEdit && category.description) {
            descInput.value = category.description;
        }
        descGroup.appendChild(descInput);
        form.appendChild(descGroup);

        // Keywords
        var kwGroup = Utils.createElement("div", { className: "form-group" });
        kwGroup.appendChild(Utils.createElement("label", {}, "Keywords"));

        var kwInputRow = Utils.createElement("div", { className: "keywords-input-group" });
        var kwInput = Utils.createElement("input", {
            id: "cat-keyword-input",
            type: "text",
            className: "form-input",
            placeholder: "Add a keyword and press Enter",
        });
        kwInput.addEventListener("keydown", function (e) {
            if (e.key === "Enter") {
                e.preventDefault();
                _addKeyword(kwInput.value.trim());
                kwInput.value = "";
            }
        });
        kwInputRow.appendChild(kwInput);
        kwInputRow.appendChild(Utils.createElement("button", {
            className: "btn btn-secondary",
            textContent: "Add",
            onClick: function () {
                _addKeyword(kwInput.value.trim());
                kwInput.value = "";
            },
        }));
        kwGroup.appendChild(kwInputRow);
        kwGroup.appendChild(Utils.createElement("div", { id: "cat-keywords-tags", className: "keyword-tags mt-8" }));
        form.appendChild(kwGroup);

        // URL Patterns
        var patternsGroup = Utils.createElement("div", { className: "form-group" });
        var patternsHeader = Utils.createElement("div", { className: "flex justify-between items-center mb-8" });
        patternsHeader.appendChild(Utils.createElement("label", {}, "URL Patterns (optional)"));
        patternsHeader.appendChild(Utils.createElement("button", {
            className: "btn btn-small btn-secondary",
            textContent: "+ Add Pattern",
            onClick: function () {
                _addPattern();
            },
        }));
        patternsGroup.appendChild(patternsHeader);
        patternsGroup.appendChild(Utils.createElement("div", { id: "cat-patterns-list", className: "rules-list" }));
        form.appendChild(patternsGroup);

        // Active toggle (only for edit)
        if (isEdit) {
            var activeGroup = Utils.createElement("div", { className: "form-group" });
            var activeLabel = Utils.createElement("label", { className: "checkbox-label" });
            var activeCheckbox = Utils.createElement("input", {
                id: "cat-active",
                type: "checkbox",
            });
            activeCheckbox.checked = category.is_active;
            activeLabel.appendChild(activeCheckbox);
            activeLabel.appendChild(document.createTextNode(" Active"));
            activeGroup.appendChild(activeLabel);
            form.appendChild(activeGroup);
        }

        // Submit
        form.appendChild(Utils.createElement("div", { className: "form-submit" }, [
            Utils.createElement("button", {
                className: "btn btn-primary",
                textContent: isEdit ? "Update" : "Create",
                onClick: function () {
                    _submitForm();
                },
            }),
        ]));

        formContainer.appendChild(form);

        // Render initial keywords and patterns
        _renderKeywordTags();
        _renderPatterns();

        formContainer.scrollIntoView({ behavior: "smooth", block: "start" });
    }

    function _hideForm() {
        var formContainer = Utils.el("category-form-container");
        if (formContainer) {
            formContainer.classList.add("hidden");
            Utils.clearElement(formContainer);
        }
        _editingId = null;
        _formKeywords = [];
        _formPatterns = [];
    }


    // ---------------------------------------------------------------------------
    //    Keyword Management
    function _addKeyword(keyword) {
        if (!keyword) {
            return;
        }
        if (_formKeywords.indexOf(keyword) === -1) {
            _formKeywords.push(keyword);
            _renderKeywordTags();
        }
    }

    function _removeKeyword(index) {
        _formKeywords.splice(index, 1);
        _renderKeywordTags();
    }

    function _renderKeywordTags() {
        var container = Utils.el("cat-keywords-tags");
        if (!container) {
            return;
        }

        Utils.clearElement(container);

        _formKeywords.forEach(function (kw, index) {
            var tag = Utils.createElement("span", { className: "keyword-tag" }, [
                document.createTextNode(kw + " "),
                Utils.createElement("span", {
                    style: "cursor: pointer; margin-left: 4px; opacity: 0.7;",
                    textContent: "\u00d7",
                    onClick: function () {
                        _removeKeyword(index);
                    },
                }),
            ]);
            container.appendChild(tag);
        });
    }


    // ---------------------------------------------------------------------------
    //    URL Pattern Management
    function _addPattern() {
        _formPatterns.push({ type: "contains", pattern: "" });
        _renderPatterns();
    }

    function _removePattern(index) {
        _formPatterns.splice(index, 1);
        _renderPatterns();
    }

    function _renderPatterns() {
        var container = Utils.el("cat-patterns-list");
        if (!container) {
            return;
        }

        Utils.clearElement(container);

        if (_formPatterns.length === 0) {
            container.appendChild(Utils.createElement("p", {
                className: "text-muted",
                textContent: "No patterns added.",
                style: "font-size: 12px;",
            }));
            return;
        }

        _formPatterns.forEach(function (pattern, index) {
            var row = Utils.createElement("div", { className: "rule-row" });

            var typeSelect = Utils.createElement("select", {
                className: "form-select",
                onChange: function () {
                    _formPatterns[index].type = typeSelect.value;
                },
            });

            var types = [
                { value: "contains", label: "Contains" },
                { value: "starts_with", label: "Starts With" },
                { value: "ends_with", label: "Ends With" },
                { value: "regex", label: "Regex" },
                { value: "domain", label: "Domain" },
            ];

            types.forEach(function (t) {
                var opt = Utils.createElement("option", {
                    value: t.value,
                    textContent: t.label,
                });
                if (t.value === pattern.type) {
                    opt.selected = true;
                }
                typeSelect.appendChild(opt);
            });
            row.appendChild(typeSelect);

            var patternInput = Utils.createElement("input", {
                type: "text",
                className: "form-input",
                placeholder: "Pattern value",
                onInput: function () {
                    _formPatterns[index].pattern = patternInput.value;
                },
            });
            patternInput.value = pattern.pattern || "";
            row.appendChild(patternInput);

            row.appendChild(Utils.createElement("button", {
                className: "btn btn-icon",
                innerHTML: "&#10005;",
                onClick: function () {
                    _removePattern(index);
                },
            }));

            container.appendChild(row);
        });
    }


    // ---------------------------------------------------------------------------
    //    Form Submission
    function _submitForm() {
        var name = Utils.el("cat-name").value.trim();
        var description = Utils.el("cat-description").value.trim() || null;

        if (!name) {
            Utils.showToast("Category name is required", "warning");
            return;
        }

        var validPatterns = _formPatterns.filter(function (p) {
            return p.pattern.trim() !== "";
        });

        var data = {
            name: name,
            description: description,
            keywords: _formKeywords.length > 0 ? _formKeywords : null,
            url_patterns: validPatterns.length > 0 ? validPatterns : null,
        };

        if (_editingId) {
            var activeCheckbox = Utils.el("cat-active");
            if (activeCheckbox) {
                data.is_active = activeCheckbox.checked;
            }

            Api.updateCategory(_editingId, data)
                .then(function () {
                    Utils.showToast("Category updated", "success");
                    _hideForm();
                    _loadCategories();
                })
                .catch(function (err) {
                    Utils.showToast("Update failed: " + err.message, "error");
                });
        } else {
            Api.createCategory(data)
                .then(function () {
                    Utils.showToast("Category created", "success");
                    _hideForm();
                    _loadCategories();
                })
                .catch(function (err) {
                    Utils.showToast("Create failed: " + err.message, "error");
                });
        }
    }


    // ---------------------------------------------------------------------------
    //    Delete
    function _deleteCategory(id, name) {
        Utils.confirmDialog(
            "Delete Category",
            "Are you sure you want to delete the category \"" + name + "\"?"
        ).then(function (confirmed) {
            if (!confirmed) {
                return;
            }
            Api.deleteCategory(id)
                .then(function () {
                    Utils.showToast("Category deleted", "success");
                    _loadCategories();
                })
                .catch(function (err) {
                    Utils.showToast("Delete failed: " + err.message, "error");
                });
        });
    }

    
    // ---------------------------------------------------------------------------
    //    Public API
    return {
        init: init,
        onActivate: onActivate,
    };

})();
