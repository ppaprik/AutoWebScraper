"use strict";

var Api = (function () {

    var BASE_URL = "/api";

    // ---------------------------------------------------------------------------
    //    Core HTTP helper
    function request(method, path, body) {
        var url = BASE_URL + path;

        var options = {
            method: method,
            headers: {
                "Content-Type": "application/json",
            },
        };

        if (body !== undefined && body !== null) {
            options.body = JSON.stringify(body);
        }

        return fetch(url, options)
            .then(function (response) {
                var contentType = response.headers.get("Content-Type") || "";
                if (contentType.indexOf("application/json") === -1 && response.ok) {
                    return response;
                }

                return response.json().then(function (data) {
                    if (!response.ok) {
                        var errorMessage = data.detail || data.message || "Request failed";
                        var error = new Error(errorMessage);
                        error.status = response.status;
                        error.data = data;
                        throw error;
                    }
                    return data;
                });
            });
    }


    // ---------------------------------------------------------------------------
    //    Health
    function getHealth() {
        return request("GET", "/health");
    }


    // ---------------------------------------------------------------------------
    //    Jobs
    function createJob(jobData) {
        return request("POST", "/jobs", jobData);
    }

    function listJobs(status, limit, offset) {
        var query = "?limit=" + (limit || 100) + "&offset=" + (offset || 0);
        if (status) {
            query += "&status=" + status;
        }
        return request("GET", "/jobs" + query);
    }

    function getJob(jobId) {
        return request("GET", "/jobs/" + jobId);
    }

    function jobAction(jobId, action) {
        return request("POST", "/jobs/" + jobId + "/action", { action: action });
    }

    function deleteJob(jobId) {
        return request("DELETE", "/jobs/" + jobId);
    }


    // ---------------------------------------------------------------------------
    //    Scrape Results
    function getScrapeResults(jobId, limit, offset) {
        var query = "?limit=" + (limit || 100) + "&offset=" + (offset || 0);
        return request("GET", "/scrape/" + jobId + "/results" + query);
    }

    function getContentVersions(url) {
        return request("GET", "/scrape/versions?url=" + encodeURIComponent(url));
    }


    // ---------------------------------------------------------------------------
    //    Categories
    function createCategory(data) {
        return request("POST", "/categories", data);
    }

    function listCategories() {
        return request("GET", "/categories");
    }

    function getCategory(categoryId) {
        return request("GET", "/categories/" + categoryId);
    }

    function updateCategory(categoryId, data) {
        return request("PUT", "/categories/" + categoryId, data);
    }

    function deleteCategory(categoryId) {
        return request("DELETE", "/categories/" + categoryId);
    }


    // ---------------------------------------------------------------------------
    //    Credentials
    function createCredential(data) {
        return request("POST", "/credentials", data);
    }

    function listCredentials() {
        return request("GET", "/credentials");
    }

    function getCredential(credentialId) {
        return request("GET", "/credentials/" + credentialId);
    }

    function updateCredential(credentialId, data) {
        return request("PUT", "/credentials/" + credentialId, data);
    }

    function deleteCredential(credentialId) {
        return request("DELETE", "/credentials/" + credentialId);
    }


    // ---------------------------------------------------------------------------
    //    Logs
    function getLogs(jobId, limit, offset) {
        var query = "?limit=" + (limit || 200) + "&offset=" + (offset || 0);
        return request("GET", "/logs/" + jobId + query);
    }


    // ---------------------------------------------------------------------------
    //    Analytics
    function getStats() {
        return request("GET", "/analytics/stats");
    }

    function getVolume(days) {
        return request("GET", "/analytics/volume?days=" + (days || 30));
    }

    function getCategoryDistribution() {
        return request("GET", "/analytics/categories");
    }

    function exportResults(jobId, format) {
        format = format || "json";
        var url = BASE_URL + "/analytics/export/" + jobId + "?format=" + format;
        return fetch(url).then(function (response) {
            if (!response.ok) {
                throw new Error("Export failed");
            }
            return response.blob();
        });
    }


    // ---------------------------------------------------------------------------
    //    Settings
    function getSettings() {
        return request("GET", "/settings");
    }

    function updateSettings(payload) {
        return request("PUT", "/settings", payload);
    }

    function getSettingsSchema() {
        return request("GET", "/settings/schema");
    }


    // ---------------------------------------------------------------------------
    //    System
    /**
     * POST /api/system/restart
     * Triggers restart of celery-worker, celery-beat, and api containers.
     * The api will go offline briefly — the caller should begin polling
     * getSystemStatus() or getHealth() immediately after this resolves.
     */
    function restartContainers() {
        return request("POST", "/system/restart");
    }

    /**
     * GET /api/system/status
     * Returns status of all tracked containers.
     * Used to poll whether everything is back up after a restart.
     */
    function getSystemStatus() {
        return request("GET", "/system/status");
    }


    // ---------------------------------------------------------------------------
    //    Public API
    return {
        getHealth: getHealth,

        createJob: createJob,
        listJobs: listJobs,
        getJob: getJob,
        jobAction: jobAction,
        deleteJob: deleteJob,

        getScrapeResults: getScrapeResults,
        getContentVersions: getContentVersions,

        createCategory: createCategory,
        listCategories: listCategories,
        getCategory: getCategory,
        updateCategory: updateCategory,
        deleteCategory: deleteCategory,

        createCredential: createCredential,
        listCredentials: listCredentials,
        getCredential: getCredential,
        updateCredential: updateCredential,
        deleteCredential: deleteCredential,

        getLogs: getLogs,

        getStats: getStats,
        getVolume: getVolume,
        getCategoryDistribution: getCategoryDistribution,
        exportResults: exportResults,

        getSettings: getSettings,
        updateSettings: updateSettings,
        getSettingsSchema: getSettingsSchema,

        restartContainers: restartContainers,
        getSystemStatus: getSystemStatus,
    };

})();
