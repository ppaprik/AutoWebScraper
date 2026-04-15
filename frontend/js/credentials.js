"use strict";

var Credentials = (function () {

    var _credentials = [];
    var _editingId = null;

    
    // ---------------------------------------------------------------------------
    //    Initialization
    function init() {
        _renderLayout();
    }

    function onActivate() {
        _loadCredentials();
    }


    // ---------------------------------------------------------------------------
    //    Layout
    function _renderLayout() {
        var container = Utils.el("view-credentials");
        if (!container) {
            return;
        }

        Utils.clearElement(container);

        // Header
        container.appendChild(Utils.createElement("div", { className: "credentials-header" }, [
            Utils.createElement("h2", {}, "Credentials Manager"),
            Utils.createElement("button", {
                id: "btn-add-credential",
                className: "btn btn-primary",
                textContent: "+ Add Credential",
                onClick: function () {
                    _showForm(null);
                },
            }),
        ]));

        // Credential list
        container.appendChild(Utils.createElement("div", { id: "credentials-list" }));

        // Form (hidden by default)
        container.appendChild(Utils.createElement("div", {
            id: "credential-form-container",
            className: "hidden",
        }));
    }


    // ---------------------------------------------------------------------------
    //    Data Loading
    function _loadCredentials() {
        Api.listCredentials()
            .then(function (data) {
                _credentials = data.credentials || [];
                _renderList();
            })
            .catch(function (err) {
                Utils.showToast("Failed to load credentials: " + err.message, "error");
            });
    }


    // ---------------------------------------------------------------------------
    //    List Rendering
    function _renderList() {
        var container = Utils.el("credentials-list");
        if (!container) {
            return;
        }

        Utils.clearElement(container);

        if (_credentials.length === 0) {
            container.appendChild(Utils.createElement("div", {
                className: "card",
                style: "text-align: center; padding: 40px;",
            }, [
                Utils.createElement("p", {
                    className: "text-muted",
                    textContent: "No credentials stored yet. Add one to enable authenticated scraping.",
                }),
            ]));
            return;
        }

        _credentials.forEach(function (cred) {
            var card = Utils.createElement("div", { className: "credential-card" });

            var info = Utils.createElement("div", { className: "credential-info" }, [
                Utils.createElement("span", { className: "credential-domain", textContent: cred.domain }),
                Utils.createElement("span", { className: "credential-username", textContent: "User: " + cred.username }),
                Utils.createElement("div", { className: "credential-meta" }, [
                    Utils.createElement("span", { className: "encryption-badge" }, [
                        document.createTextNode("&#9919; Encrypted"),
                    ]),
                    Utils.createElement("span", {
                        textContent: "Added " + Utils.formatDate(cred.created_at),
                    }),
                ]),
            ]);
            card.appendChild(info);

            var actions = Utils.createElement("div", { className: "credential-actions" }, [
                Utils.createElement("button", {
                    className: "btn btn-small btn-secondary",
                    textContent: "Edit",
                    onClick: function () {
                        _showForm(cred);
                    },
                }),
                Utils.createElement("button", {
                    className: "btn btn-small btn-danger",
                    textContent: "Delete",
                    onClick: function () {
                        _deleteCredential(cred.id, cred.domain);
                    },
                }),
            ]);
            card.appendChild(actions);

            container.appendChild(card);
        });
    }


    // ---------------------------------------------------------------------------
    //    Form
    function _showForm(credential) {
        _editingId = credential ? credential.id : null;

        var formContainer = Utils.el("credential-form-container");
        if (!formContainer) {
            return;
        }

        Utils.clearElement(formContainer);
        formContainer.classList.remove("hidden");

        var isEdit = credential !== null;
        var title = isEdit ? "Edit Credential" : "Add Credential";

        var form = Utils.createElement("div", { className: "card credential-form mt-24" });

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

        // Domain
        var domainGroup = Utils.createElement("div", { className: "form-group" });
        domainGroup.appendChild(Utils.createElement("label", {}, "Domain"));
        var domainInput = Utils.createElement("input", {
            id: "cred-domain",
            type: "text",
            className: "form-input",
            placeholder: "example.com",
            value: isEdit ? credential.domain : "",
        });
        if (isEdit) {
            domainInput.value = credential.domain;
        }
        domainGroup.appendChild(domainInput);
        form.appendChild(domainGroup);

        // Username
        var userGroup = Utils.createElement("div", { className: "form-group" });
        userGroup.appendChild(Utils.createElement("label", {}, "Username"));
        var userInput = Utils.createElement("input", {
            id: "cred-username",
            type: "text",
            className: "form-input",
            placeholder: "your_username",
            value: isEdit ? credential.username : "",
        });
        if (isEdit) {
            userInput.value = credential.username;
        }
        userGroup.appendChild(userInput);
        form.appendChild(userGroup);

        // Password
        var passGroup = Utils.createElement("div", { className: "form-group" });
        passGroup.appendChild(Utils.createElement("label", {}, isEdit ? "New Password (leave blank to keep current)" : "Password"));
        passGroup.appendChild(Utils.createElement("input", {
            id: "cred-password",
            type: "password",
            className: "form-input",
            placeholder: isEdit ? "Leave blank to keep existing" : "Enter password",
        }));
        form.appendChild(passGroup);

        // Login URL
        var loginGroup = Utils.createElement("div", { className: "form-group" });
        loginGroup.appendChild(Utils.createElement("label", {}, "Login URL (optional)"));
        var loginInput = Utils.createElement("input", {
            id: "cred-login-url",
            type: "url",
            className: "form-input",
            placeholder: "https://example.com/login",
            value: isEdit && credential.login_url ? credential.login_url : "",
        });
        if (isEdit && credential.login_url) {
            loginInput.value = credential.login_url;
        }
        loginGroup.appendChild(loginInput);
        loginGroup.appendChild(Utils.createElement("p", {
            className: "form-hint",
            textContent: "The URL where the login form is located.",
        }));
        form.appendChild(loginGroup);

        // Selectors row
        var selectorRow = Utils.createElement("div", { className: "form-row" });

        var uSelGroup = Utils.createElement("div", { className: "form-group" });
        uSelGroup.appendChild(Utils.createElement("label", {}, "Username Selector"));
        var uSelInput = Utils.createElement("input", {
            id: "cred-user-selector",
            type: "text",
            className: "form-input",
            placeholder: "input[name=\"email\"]",
        });
        if (isEdit && credential.username_selector) {
            uSelInput.value = credential.username_selector;
        }
        uSelGroup.appendChild(uSelInput);
        selectorRow.appendChild(uSelGroup);

        var pSelGroup = Utils.createElement("div", { className: "form-group" });
        pSelGroup.appendChild(Utils.createElement("label", {}, "Password Selector"));
        var pSelInput = Utils.createElement("input", {
            id: "cred-pass-selector",
            type: "text",
            className: "form-input",
            placeholder: "input[name=\"password\"]",
        });
        if (isEdit && credential.password_selector) {
            pSelInput.value = credential.password_selector;
        }
        pSelGroup.appendChild(pSelInput);
        selectorRow.appendChild(pSelGroup);

        form.appendChild(selectorRow);

        // Submit
        form.appendChild(Utils.createElement("div", { className: "form-submit" }, [
            Utils.createElement("button", {
                className: "btn btn-primary",
                textContent: isEdit ? "Update" : "Save",
                onClick: function () {
                    _submitForm();
                },
            }),
        ]));

        formContainer.appendChild(form);

        // Scroll to form
        formContainer.scrollIntoView({ behavior: "smooth", block: "start" });
    }

    function _hideForm() {
        var formContainer = Utils.el("credential-form-container");
        if (formContainer) {
            formContainer.classList.add("hidden");
            Utils.clearElement(formContainer);
        }
        _editingId = null;
    }

    function _submitForm() {
        var domain = Utils.el("cred-domain").value.trim();
        var username = Utils.el("cred-username").value.trim();
        var password = Utils.el("cred-password").value;
        var loginUrl = Utils.el("cred-login-url").value.trim() || null;
        var userSelector = Utils.el("cred-user-selector").value.trim() || null;
        var passSelector = Utils.el("cred-pass-selector").value.trim() || null;

        if (!domain) {
            Utils.showToast("Domain is required", "warning");
            return;
        }
        if (!username) {
            Utils.showToast("Username is required", "warning");
            return;
        }

        if (_editingId) {
            // Update
            var updateData = {
                domain: domain,
                username: username,
                login_url: loginUrl,
                username_selector: userSelector,
                password_selector: passSelector,
            };
            if (password) {
                updateData.password = password;
            }

            Api.updateCredential(_editingId, updateData)
                .then(function () {
                    Utils.showToast("Credential updated", "success");
                    _hideForm();
                    _loadCredentials();
                })
                .catch(function (err) {
                    Utils.showToast("Update failed: " + err.message, "error");
                });
        } else {
            // Create
            if (!password) {
                Utils.showToast("Password is required for new credentials", "warning");
                return;
            }

            Api.createCredential({
                domain: domain,
                username: username,
                password: password,
                login_url: loginUrl,
                username_selector: userSelector,
                password_selector: passSelector,
            })
                .then(function () {
                    Utils.showToast("Credential saved", "success");
                    _hideForm();
                    _loadCredentials();
                })
                .catch(function (err) {
                    Utils.showToast("Save failed: " + err.message, "error");
                });
        }
    }


    // ---------------------------------------------------------------------------
    //    Delete
    function _deleteCredential(id, domain) {
        Utils.confirmDialog(
            "Delete Credential",
            "Are you sure you want to delete the credential for \"" + domain + "\"?"
        ).then(function (confirmed) {
            if (!confirmed) {
                return;
            }
            Api.deleteCredential(id)
                .then(function () {
                    Utils.showToast("Credential deleted", "success");
                    _loadCredentials();
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
