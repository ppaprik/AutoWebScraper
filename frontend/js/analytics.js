"use strict";

var Analytics = (function () {

    var _chartColors = [
        "#4f8ff7", "#34c759", "#ff9f0a", "#af52de",
        "#ff453a", "#ffd60a", "#5ac8fa", "#ff6482",
    ];


    // ---------------------------------------------------------------------------
    //    Initialization
    function init() {
        _renderLayout();
    }

    function onActivate() {
        _loadStats();
        _loadVolume();
        _loadCategories();
        _loadJobsForExport();
    }


    // ---------------------------------------------------------------------------
    //    Layout
    function _renderLayout() {
        var container = Utils.el("view-analytics");
        if (!container) {
            return;
        }

        Utils.clearElement(container);

        // Header
        container.appendChild(Utils.createElement("div", { className: "view-header" }, [
            Utils.createElement("h2", {}, "Analytics"),
            Utils.createElement("button", {
                className: "btn btn-secondary",
                textContent: "↻ Refresh",
                onClick: function () {
                    onActivate();
                },
            }),
        ]));

        // Stats cards row
        var statsGrid = Utils.createElement("div", {
            id: "analytics-stats",
            className: "metrics-bar",
        });
        container.appendChild(statsGrid);

        // Charts row
        var chartsGrid = Utils.createElement("div", { className: "analytics-grid" });

        // Volume chart
        var volumeCard = Utils.createElement("div", { className: "chart-card" }, [
            Utils.createElement("h3", {}, "Scrape Volume (Last 30 Days)"),
            Utils.createElement("div", { id: "volume-chart", className: "bar-chart" }),
        ]);
        chartsGrid.appendChild(volumeCard);

        // Category distribution
        var catCard = Utils.createElement("div", { className: "chart-card" }, [
            Utils.createElement("h3", {}, "Jobs by Category"),
            Utils.createElement("div", { id: "category-chart", className: "pie-chart" }),
        ]);
        chartsGrid.appendChild(catCard);

        container.appendChild(chartsGrid);

        // Export bar
        var exportBar = Utils.createElement("div", { className: "export-bar" }, [
            Utils.createElement("label", {}, "Export Results:"),
            Utils.createElement("select", { id: "export-job-select", className: "form-select", style: "max-width: 300px;" }, [
                Utils.createElement("option", { value: "" }, "Select a job..."),
            ]),
            Utils.createElement("button", {
                className: "btn btn-secondary",
                textContent: "Export JSON",
                onClick: function () {
                    _exportResults("json");
                },
            }),
            Utils.createElement("button", {
                className: "btn btn-secondary",
                textContent: "Export CSV",
                onClick: function () {
                    _exportResults("csv");
                },
            }),
        ]);
        container.appendChild(exportBar);
    }


    // ---------------------------------------------------------------------------
    //    Stats
    function _loadStats() {
        Api.getStats()
            .then(function (stats) {
                _renderStats(stats);
            })
            .catch(function () {
                // Show empty stats
            });
    }

    function _renderStats(stats) {
        var container = Utils.el("analytics-stats");
        if (!container) {
            return;
        }

        Utils.clearElement(container);

        var cards = [
            { label: "Total Jobs", value: stats.total_jobs },
            { label: "Pages Scraped", value: stats.total_pages_scraped },
            { label: "Content Versions", value: stats.total_content_versions },
            { label: "Total Errors", value: stats.total_errors },
        ];

        cards.forEach(function (card) {
            container.appendChild(Utils.createElement("div", { className: "metric-card" }, [
                Utils.createElement("span", {
                    className: "metric-value",
                    textContent: Utils.formatNumber(card.value),
                }),
                Utils.createElement("span", {
                    className: "metric-label",
                    textContent: card.label,
                }),
            ]));
        });
    }


    // ---------------------------------------------------------------------------
    //    Volume Chart (CSS-only bar chart)
    function _loadVolume() {
        Api.getVolume(30)
            .then(function (data) {
                _renderVolumeChart(data);
            })
            .catch(function () {
                // Show empty chart
            });
    }

    function _renderVolumeChart(data) {
        var container = Utils.el("volume-chart");
        if (!container) {
            return;
        }

        Utils.clearElement(container);

        if (!data || data.length === 0) {
            container.appendChild(Utils.createElement("p", {
                className: "text-muted text-center",
                textContent: "No data available yet.",
                style: "padding: 60px 0;",
            }));
            return;
        }

        // Find max value for scaling
        var maxVal = 0;
        data.forEach(function (d) {
            if (d.count > maxVal) {
                maxVal = d.count;
            }
        });

        if (maxVal === 0) {
            maxVal = 1;
        }

        // Render bars (show last 14 days max for readability)
        var displayData = data.slice(-14);

        displayData.forEach(function (d) {
            var heightPercent = (d.count / maxVal) * 100;
            var dateStr = d.day.substring(5, 10);

            var column = Utils.createElement("div", { className: "bar-column" }, [
                Utils.createElement("span", {
                    className: "bar-value",
                    textContent: d.count > 0 ? String(d.count) : "",
                }),
                Utils.createElement("div", {
                    className: "bar",
                    style: "height: " + heightPercent + "%;",
                }),
                Utils.createElement("span", {
                    className: "bar-label",
                    textContent: dateStr,
                }),
            ]);

            container.appendChild(column);
        });
    }


    // ---------------------------------------------------------------------------
    //    Category Distribution
    function _loadCategories() {
        Api.getCategoryDistribution()
            .then(function (data) {
                _renderCategoryChart(data);
            })
            .catch(function () {
                // Show empty chart
            });
    }

    function _renderCategoryChart(data) {
        var container = Utils.el("category-chart");
        if (!container) {
            return;
        }

        Utils.clearElement(container);

        if (!data || data.length === 0) {
            container.appendChild(Utils.createElement("p", {
                className: "text-muted text-center",
                textContent: "No categories with jobs yet.",
                style: "padding: 40px 0;",
            }));
            return;
        }

        var legend = Utils.createElement("div", { className: "pie-legend" });

        data.forEach(function (entry, index) {
            var color = _chartColors[index % _chartColors.length];

            var item = Utils.createElement("div", { className: "pie-legend-item" }, [
                Utils.createElement("span", {
                    className: "pie-legend-dot",
                    style: "background-color: " + color + ";",
                }),
                document.createTextNode(entry.category + " (" + entry.job_count + " jobs)"),
            ]);

            legend.appendChild(item);
        });

        container.appendChild(legend);
    }


    // ---------------------------------------------------------------------------
    //    Export
    function _loadJobsForExport() {
        Api.listJobs(null, 50)
            .then(function (data) {
                var select = Utils.el("export-job-select");
                if (!select) {
                    return;
                }

                // Clear existing options (keep first)
                while (select.options.length > 1) {
                    select.remove(1);
                }

                (data.jobs || []).forEach(function (job) {
                    select.appendChild(Utils.createElement("option", {
                        value: job.id,
                        textContent: job.name + " (" + job.pages_scraped + " pages)",
                    }));
                });
            })
            .catch(function () {
                // Silently fail
            });
    }

    function _exportResults(format) {
        var select = Utils.el("export-job-select");
        if (!select || !select.value) {
            Utils.showToast("Please select a job to export", "warning");
            return;
        }

        var jobId = select.value;

        Api.exportResults(jobId, format)
            .then(function (blob) {
                // Create a download link
                var url = URL.createObjectURL(blob);
                var a = document.createElement("a");
                a.href = url;
                a.download = "scrape_results_" + jobId.substring(0, 8) + "." + format;
                document.body.appendChild(a);
                a.click();
                document.body.removeChild(a);
                URL.revokeObjectURL(url);
                Utils.showToast("Export downloaded", "success");
            })
            .catch(function (err) {
                Utils.showToast("Export failed: " + err.message, "error");
            });
    }


    // ---------------------------------------------------------------------------
    //    Public API
    return {
        init: init,
        onActivate: onActivate,
    };

})();
