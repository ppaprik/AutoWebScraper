"use strict";

var Utils = (function () {
    // ---------------------------------------------------------------------------
    //    DOM Helpers
    function el(id) {
        return document.getElementById(id);
    }

    function qs(selector, parent) {
        return (parent || document).querySelector(selector);
    }

    function qsa(selector, parent) {
        return Array.from((parent || document).querySelectorAll(selector));
    }

    function createElement(tag, attrs, children) {
        var element = document.createElement(tag);

        if (attrs) {
            Object.keys(attrs).forEach(function (key) {
                if (key === "className") {
                    element.className = attrs[key];
                } else if (key === "textContent") {
                    element.textContent = attrs[key];
                } else if (key === "innerHTML") {
                    element.innerHTML = attrs[key];
                } else if (key.startsWith("on")) {
                    element.addEventListener(key.substring(2).toLowerCase(), attrs[key]);
                } else if (key === "dataset") {
                    Object.keys(attrs[key]).forEach(function (dataKey) {
                        element.dataset[dataKey] = attrs[key][dataKey];
                    });
                } else {
                    element.setAttribute(key, attrs[key]);
                }
            });
        }

        if (children) {
            if (typeof children === "string") {
                element.textContent = children;
            } else if (Array.isArray(children)) {
                children.forEach(function (child) {
                    if (typeof child === "string") {
                        element.appendChild(document.createTextNode(child));
                    } else if (child instanceof Node) {
                        element.appendChild(child);
                    }
                });
            } else if (children instanceof Node) {
                element.appendChild(children);
            }
        }

        return element;
    }

    function clearElement(element) {
        while (element.firstChild) {
            element.removeChild(element.firstChild);
        }
    }


    // ---------------------------------------------------------------------------
    //    Formatters
    function formatDate(dateStr) {
        if (!dateStr) { return "—"; }

        var date = new Date(dateStr);
        if (isNaN(date.getTime())) { return "—"; }

        var now = new Date();
        var diffMs = now - date;
        var diffSec = Math.floor(diffMs / 1000);
        var diffMin = Math.floor(diffSec / 60);
        var diffHour = Math.floor(diffMin / 60);

        if (diffSec < 60)  { return "just now"; }
        if (diffMin < 60)  { return diffMin + "m ago"; }
        if (diffHour < 24) { return diffHour + "h ago"; }

        return date.toLocaleDateString("en-US", {
            month: "short",
            day: "numeric",
            hour: "2-digit",
            minute: "2-digit",
        });
    }

    function formatLogTime(dateStr) {
        if (!dateStr) { return ""; }
        var date = new Date(dateStr);
        return date.toLocaleTimeString("en-US", {
            hour12: false,
            hour: "2-digit",
            minute: "2-digit",
            second: "2-digit",
        });
    }

    function truncateUrl(url, maxLength) {
        maxLength = maxLength || 50;
        if (!url) { return "—"; }
        if (url.length <= maxLength) { return url; }
        return url.substring(0, maxLength) + "...";
    }

    function formatNumber(num) {
        if (num === null || num === undefined) { return "0"; }
        return num.toLocaleString("en-US");
    }

    function formatSpeed(pps) {
        if (!pps || pps === 0) { return "—"; }

        var pph = pps * 3600;

        if (pph >= 1000) {
            return (pph / 1000).toFixed(1) + "k p/h";
        }
        if (pph >= 10) {
            return Math.round(pph) + " p/h";
        }
        return pph.toFixed(1) + " p/h";
    }

    function formatCrawlMode(mode) {
        var labels = {
            "single":     "Single",
            "rule_based": "Rule-Based",
            "infinite":   "Infinite",
            "category":   "Category",
        };
        return labels[mode] || mode;
    }


    // ---------------------------------------------------------------------------
    //    Toast Notifications
    function showToast(message, type, duration) {
        type = type || "info";
        duration = duration || 4000;

        var container = el("toast-container");
        if (!container) { return; }

        var toast = createElement("div", {
            className: "toast " + type,
            textContent: message,
        });

        container.appendChild(toast);

        setTimeout(function () {
            toast.classList.add("fade-out");
            setTimeout(function () {
                if (toast.parentNode) {
                    toast.parentNode.removeChild(toast);
                }
            }, 300);
        }, duration);
    }


    // ---------------------------------------------------------------------------
    //    Modal Helpers
    function confirmDialog(title, message) {
        return new Promise(function (resolve) {
            var overlay = createElement("div", { className: "modal-overlay" });
            var modal   = createElement("div", { className: "modal" });

            var header = createElement("div", { className: "modal-header" }, [
                createElement("h3", {}, title),
            ]);

            var body = createElement("p", {
                textContent: message,
                style: "color: var(--text-secondary); margin-bottom: 8px;",
            });

            var footer = createElement("div", { className: "modal-footer" }, [
                createElement("button", {
                    className: "btn btn-secondary",
                    textContent: "Cancel",
                    onClick: function () {
                        document.body.removeChild(overlay);
                        resolve(false);
                    },
                }),
                createElement("button", {
                    className: "btn btn-danger",
                    textContent: "Confirm",
                    onClick: function () {
                        document.body.removeChild(overlay);
                        resolve(true);
                    },
                }),
            ]);

            modal.appendChild(header);
            modal.appendChild(body);
            modal.appendChild(footer);
            overlay.appendChild(modal);

            overlay.addEventListener("click", function (e) {
                if (e.target === overlay) {
                    document.body.removeChild(overlay);
                    resolve(false);
                }
            });

            document.body.appendChild(overlay);
        });
    }


    // ---------------------------------------------------------------------------
    //    Debounce
    function debounce(fn, delay) {
        var timer = null;
        return function () {
            var context = this;
            var args = arguments;
            clearTimeout(timer);
            timer = setTimeout(function () {
                fn.apply(context, args);
            }, delay);
        };
    }

    
    // ---------------------------------------------------------------------------
    //    Public API
    return {
        el: el,
        qs: qs,
        qsa: qsa,
        createElement: createElement,
        clearElement: clearElement,
        formatDate: formatDate,
        formatLogTime: formatLogTime,
        truncateUrl: truncateUrl,
        formatNumber: formatNumber,
        formatSpeed: formatSpeed,
        formatCrawlMode: formatCrawlMode,
        showToast: showToast,
        confirmDialog: confirmDialog,
        debounce: debounce,
    };

})();
