"use strict";

var Dashboard = (function () {

    var _refreshTimer = null;
    var _refreshInterval = 5000;
    var _currentFilter = null;
    var _logJobId = null;


    // ---------------------------------------------------------------------------
    //    Initialization
    function init() {
        // Bind the refresh button
        var refreshBtn = Utils.el("btn-refresh-jobs");
        if (refreshBtn) {
            refreshBtn.addEventListener("click", function () {
                loadJobs();
            });
        }

        // Bind close log panel button
        var closeLogsBtn = Utils.el("btn-close-logs");
        if (closeLogsBtn) {
            closeLogsBtn.addEventListener("click", closeLogPanel);
        }
    }

    //    Called whenever the dashboard view becomes active.
    function onActivate() {
        loadJobs();
        _startAutoRefresh();
    }

    
    // ---------------------------------------------------------------------------
    //    Job List
    function loadJobs() {
        Api.listJobs(_currentFilter)
            .then(function (data) {
                _renderJobsTable(data.jobs);
                _updateMetrics(data.jobs);
            })
            .catch(function (err) {
                Utils.showToast("Failed to load jobs: " + err.message, "error");
            });
    }

    /**
     * Render the jobs table rows.
     */
    function _renderJobsTable(jobs) {
        var tbody = Utils.el("jobs-table-body");
        if (!tbody) {
            return;
        }

        Utils.clearElement(tbody);

        if (!jobs || jobs.length === 0) {
            var emptyRow = Utils.createElement("tr", {}, [
                Utils.createElement("td", {
                    colspan: "8",
                    className: "empty-state",
                    textContent: "No jobs yet. Create one to get started.",
                }),
            ]);
            tbody.appendChild(emptyRow);
            return;
        }

        jobs.forEach(function (job) {
            var row = _createJobRow(job);
            tbody.appendChild(row);
        });
    }

    // ---------------------------------------------------------------------------
    // Create a single table row for a job.
    function _createJobRow(job) {
        var row = Utils.createElement("tr", { className: "clickable" });

        // Name
        row.appendChild(Utils.createElement("td", {
            textContent: job.name,
            title: job.name,
        }));

        // URL
        var urlTd = Utils.createElement("td");
        var urlSpan = Utils.createElement("span", {
            className: "url-text",
            textContent: Utils.truncateUrl(job.start_url, 40),
            title: job.start_url,
        });
        urlTd.appendChild(urlSpan);
        row.appendChild(urlTd);

        // Mode
        row.appendChild(Utils.createElement("td", {
            textContent: Utils.formatCrawlMode(job.crawl_mode),
        }));

        // Status badge
        var statusTd = Utils.createElement("td");
        var badge = Utils.createElement("span", {
            className: "status-badge " + job.status,
            textContent: job.status,
        });
        statusTd.appendChild(badge);
        row.appendChild(statusTd);

        // Pages
        var pagesText = Utils.formatNumber(job.pages_scraped);
        if (job.pages_failed > 0) {
            pagesText += " / " + Utils.formatNumber(job.pages_failed) + " err";
        }
        row.appendChild(Utils.createElement("td", { textContent: pagesText }));

        // Speed
        row.appendChild(Utils.createElement("td", {
            textContent: Utils.formatSpeed(job.pages_per_second),
        }));

        // Created
        row.appendChild(Utils.createElement("td", {
            textContent: Utils.formatDate(job.created_at),
        }));

        // Actions
        var actionsTd = Utils.createElement("td");
        var actionsDiv = Utils.createElement("div", { className: "job-actions" });
        actionsDiv.appendChild(_createActionButtons(job));
        actionsTd.appendChild(actionsDiv);
        row.appendChild(actionsTd);

        // Click row to open logs (except the actions column)
        row.addEventListener("click", function (e) {
            if (e.target.closest(".job-actions")) {
                return;
            }
            openLogPanel(job.id, job.name);
        });

        return row;
    }

    // ---------------------------------------------------------------------------
    // Create action buttons appropriate for the job's current status.
    function _createActionButtons(job) {
        var fragment = document.createDocumentFragment();

        if (job.status === "running") {
            // Pause button
            fragment.appendChild(Utils.createElement("button", {
                className: "btn btn-small btn-warning",
                title: "Pause",
                innerHTML: "&#9208;",
                onClick: function (e) {
                    e.stopPropagation();
                    _jobAction(job.id, "pause");
                },
            }));

            // Stop button
            fragment.appendChild(Utils.createElement("button", {
                className: "btn btn-small btn-danger",
                title: "Stop",
                innerHTML: "&#9724;",
                onClick: function (e) {
                    e.stopPropagation();
                    _jobAction(job.id, "stop");
                },
            }));
        } else if (job.status === "paused") {
            // Resume button
            fragment.appendChild(Utils.createElement("button", {
                className: "btn btn-small btn-success",
                title: "Resume",
                innerHTML: "&#9654;",
                onClick: function (e) {
                    e.stopPropagation();
                    _jobAction(job.id, "resume");
                },
            }));

            // Stop button
            fragment.appendChild(Utils.createElement("button", {
                className: "btn btn-small btn-danger",
                title: "Stop",
                innerHTML: "&#9724;",
                onClick: function (e) {
                    e.stopPropagation();
                    _jobAction(job.id, "stop");
                },
            }));
        } else if (job.status === "pending") {
            // Stop button
            fragment.appendChild(Utils.createElement("button", {
                className: "btn btn-small btn-danger",
                title: "Cancel",
                innerHTML: "&#9724;",
                onClick: function (e) {
                    e.stopPropagation();
                    _jobAction(job.id, "stop");
                },
            }));
        }

        // View logs button (always available)
        fragment.appendChild(Utils.createElement("button", {
            className: "btn btn-small btn-secondary",
            title: "View Logs",
            innerHTML: "&#9776;",
            onClick: function (e) {
                e.stopPropagation();
                openLogPanel(job.id, job.name);
            },
        }));

        // Delete button (only for terminal states)
        if (job.status === "completed" || job.status === "failed" || job.status === "stopped") {
            fragment.appendChild(Utils.createElement("button", {
                className: "btn btn-small btn-danger",
                title: "Delete",
                innerHTML: "&#10005;",
                onClick: function (e) {
                    e.stopPropagation();
                    _deleteJob(job.id, job.name);
                },
            }));
        }

        return fragment;
    }


    // ---------------------------------------------------------------------------
    //    Job Actions
    function _jobAction(jobId, action) {
        Api.jobAction(jobId, action)
            .then(function (data) {
                Utils.showToast(data.message, "success");
                loadJobs();
            })
            .catch(function (err) {
                Utils.showToast("Action failed: " + err.message, "error");
            });
    }

    function _deleteJob(jobId, jobName) {
        Utils.confirmDialog(
            "Delete Job",
            "Are you sure you want to delete \"" + jobName + "\"? All scrape results and logs will be permanently removed."
        ).then(function (confirmed) {
            if (!confirmed) {
                return;
            }
            Api.deleteJob(jobId)
                .then(function () {
                    Utils.showToast("Job deleted", "success");
                    if (_logJobId === jobId) {
                        closeLogPanel();
                    }
                    loadJobs();
                })
                .catch(function (err) {
                    Utils.showToast("Delete failed: " + err.message, "error");
                });
        });
    }


    // ---------------------------------------------------------------------------
    //    Live Log Panel
    function openLogPanel(jobId, jobName) {
        var panel = Utils.el("log-panel");
        var jobNameEl = Utils.el("log-job-name");
        var logStream = Utils.el("log-stream");

        if (!panel || !logStream) {
            return;
        }

        // Close existing stream
        WS.disconnect();
        _logJobId = jobId;

        // Update UI
        panel.classList.remove("hidden");
        if (jobNameEl) {
            jobNameEl.textContent = jobName || jobId;
        }
        Utils.clearElement(logStream);

        // Load existing logs first
        Api.getLogs(jobId, null, 100)
            .then(function (data) {
                // Render existing entries (they come newest-first, reverse for display)
                var entries = data.entries.slice().reverse();
                entries.forEach(function (entry) {
                    _appendLogEntry(logStream, entry);
                });
                _scrollToBottom(logStream);
            })
            .catch(function () {
                // Silently fail — WebSocket will pick up new logs
            });

        // Connect WebSocket for real-time streaming
        WS.connect(jobId, {
            onLogEntry: function (entry) {
                _appendLogEntry(logStream, entry);
                _scrollToBottom(logStream);
            },
            onStatusUpdate: function (status) {
                // Refresh the job list to update badges and metrics
                loadJobs();
            },
            onJobFinished: function (data) {
                _appendSystemMessage(logStream, "Job finished with status: " + data.status);
                loadJobs();
            },
            onConnectionChange: function (connected) {
                if (!connected && _logJobId) {
                    _appendSystemMessage(logStream, "Connection lost. Reconnecting...");
                }
            },
        });
    }

    function closeLogPanel() {
        var panel = Utils.el("log-panel");
        if (panel) {
            panel.classList.add("hidden");
        }
        WS.disconnect();
        _logJobId = null;
    }


    // ---------------------------------------------------------------------------
    // Append a log entry to the log stream panel.
    function _appendLogEntry(container, entry) {
        var div = Utils.createElement("div", { className: "log-entry" }, [
            Utils.createElement("span", {
                className: "log-time",
                textContent: Utils.formatLogTime(entry.created_at),
            }),
            Utils.createElement("span", {
                className: "log-level " + (entry.level || "info"),
                textContent: (entry.level || "info").toUpperCase(),
            }),
            Utils.createElement("span", {
                className: "log-message",
                textContent: entry.message,
            }),
        ]);
        container.appendChild(div);
    }


    // ---------------------------------------------------------------------------
    // Append a system message to the log stream.
    function _appendSystemMessage(container, message) {
        var div = Utils.createElement("div", {
            className: "log-entry",
            style: "opacity: 0.6; font-style: italic;",
        }, [
            Utils.createElement("span", {
                className: "log-time",
                textContent: Utils.formatLogTime(new Date().toISOString()),
            }),
            Utils.createElement("span", {
                className: "log-level info",
                textContent: "SYSTEM",
            }),
            Utils.createElement("span", {
                className: "log-message",
                textContent: message,
            }),
        ]);
        container.appendChild(div);
    }


    // ---------------------------------------------------------------------------
    // Scroll the log stream to the bottom.
    function _scrollToBottom(container) {
        container.scrollTop = container.scrollHeight;
    }

    // ---------------------------------------------------------------------------
    //    Metrics Bar
    function _updateMetrics(jobs) {
        var totalJobs = jobs.length;
        var running = 0;
        var totalPages = 0;
        var totalErrors = 0;

        jobs.forEach(function (job) {
            if (job.status === "running") {
                running++;
            }
            totalPages += job.pages_scraped || 0;
            totalErrors += job.pages_failed || 0;
        });

        _setMetric("metric-total-jobs", totalJobs);
        _setMetric("metric-running", running);
        _setMetric("metric-pages", totalPages);
        _setMetric("metric-errors", totalErrors);
    }

    function _setMetric(elementId, value) {
        var el = Utils.el(elementId);
        if (el) {
            el.textContent = Utils.formatNumber(value);
        }
    }

    // ---------------------------------------------------------------------------
    //    Auto-Refresh
    function _startAutoRefresh() {
        _stopAutoRefresh();
        _refreshTimer = setInterval(function () {
            loadJobs();
        }, _refreshInterval);
    }

    function _stopAutoRefresh() {
        if (_refreshTimer) {
            clearInterval(_refreshTimer);
            _refreshTimer = null;
        }
    }

    
    // ---------------------------------------------------------------------------
    //    Public API
    return {
        init: init,
        onActivate: onActivate,
        loadJobs: loadJobs,
        openLogPanel: openLogPanel,
        closeLogPanel: closeLogPanel,
    };

})();
