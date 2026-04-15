"use strict";

var App = (function () {

    var _currentView = "dashboard";
    var _healthTimer = null;


    // ---------------------------------------------------------------------------
    //    Initialization
    function init() {
        _bindNavigation();
        _startHealthPolling();
        _navigateTo("dashboard");

        // Initialize all view modules
        if (typeof Dashboard !== "undefined" && Dashboard.init) {
            Dashboard.init();
        }
        if (typeof JobConfig !== "undefined" && JobConfig.init) {
            JobConfig.init();
        }
        if (typeof Analytics !== "undefined" && Analytics.init) {
            Analytics.init();
        }
        if (typeof Credentials !== "undefined" && Credentials.init) {
            Credentials.init();
        }
        if (typeof Categories !== "undefined" && Categories.init) {
            Categories.init();
        }
        if (typeof Settings !== "undefined" && Settings.init) {
            Settings.init();
        }
    }

    // ---------------------------------------------------------------------------
    //    Navigation
    function _bindNavigation() {
        var navLinks = Utils.qsa(".nav-link");
        navLinks.forEach(function (link) {
            link.addEventListener("click", function (e) {
                e.preventDefault();
                var viewName = link.dataset.view;
                if (viewName) {
                    _navigateTo(viewName);
                }
            });
        });
    }

    function _navigateTo(viewName) {
        _currentView = viewName;

        // Update nav link active state
        Utils.qsa(".nav-link").forEach(function (link) {
            if (link.dataset.view === viewName) {
                link.classList.add("active");
            } else {
                link.classList.remove("active");
            }
        });

        // Show/hide view sections
        Utils.qsa(".view").forEach(function (view) {
            var viewId = view.id.replace("view-", "");
            if (viewId === viewName) {
                view.classList.add("active");
            } else {
                view.classList.remove("active");
            }
        });

        // Trigger view-specific load callbacks
        if (viewName === "dashboard" && typeof Dashboard !== "undefined") {
            Dashboard.onActivate();
        } else if (viewName === "job-config" && typeof JobConfig !== "undefined") {
            JobConfig.onActivate();
        } else if (viewName === "analytics" && typeof Analytics !== "undefined") {
            Analytics.onActivate();
        } else if (viewName === "credentials" && typeof Credentials !== "undefined") {
            Credentials.onActivate();
        } else if (viewName === "categories" && typeof Categories !== "undefined") {
            Categories.onActivate();
        } else if (viewName === "settings" && typeof Settings !== "undefined") {
            Settings.onActivate();
        }
    }


    // ---------------------------------------------------------------------------
    //    Health Check Polling
    function _startHealthPolling() {
        _checkHealth();
        _healthTimer = setInterval(_checkHealth, 15000);
    }

    function _checkHealth() {
        Api.getHealth()
            .then(function (data) {
                _updateHealthIndicator(data.status, data);
            })
            .catch(function () {
                _updateHealthIndicator("error", null);
            });
    }

    function _updateHealthIndicator(status, data) {
        var dot = Utils.qs(".health-dot");
        var text = Utils.qs(".health-text");

        if (!dot || !text) {
            return;
        }

        dot.className = "health-dot";
        if (status === "healthy") {
            dot.classList.add("healthy");
            text.textContent = "Healthy";
        } else if (status === "degraded") {
            dot.classList.add("degraded");
            text.textContent = "Degraded";
        } else {
            dot.classList.add("error");
            text.textContent = "Offline";
        }
    }


    // ---------------------------------------------------------------------------
    //    Public API
    return {
        init: init,
        navigateTo: _navigateTo,
    };

}());

// Boot the app when the DOM is ready
document.addEventListener("DOMContentLoaded", function () {
    App.init();
});
