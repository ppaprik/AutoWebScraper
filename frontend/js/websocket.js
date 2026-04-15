"use strict";

var WS = (function () {

    var _socket = null;
    var _jobId = null;
    var _reconnectTimer = null;
    var _reconnectAttempts = 0;
    var _maxReconnectAttempts = 10;
    var _reconnectDelay = 2000;

    // Callbacks
    var _onLogEntry = null;
    var _onStatusUpdate = null;
    var _onJobFinished = null;
    var _onConnectionChange = null;


    // ---------------------------------------------------------------------------
    //    Public API
    function connect(jobId, callbacks) {
        // Disconnect any existing connection first
        disconnect();

        _jobId = jobId;
        _reconnectAttempts = 0;

        if (callbacks) {
            _onLogEntry = callbacks.onLogEntry || null;
            _onStatusUpdate = callbacks.onStatusUpdate || null;
            _onJobFinished = callbacks.onJobFinished || null;
            _onConnectionChange = callbacks.onConnectionChange || null;
        }

        _createConnection();
    }

    function disconnect() {
        if (_reconnectTimer) {
            clearTimeout(_reconnectTimer);
            _reconnectTimer = null;
        }

        if (_socket) {
            _socket.onclose = null;
            _socket.onerror = null;
            _socket.onmessage = null;
            _socket.onopen = null;

            if (_socket.readyState === WebSocket.OPEN ||
                _socket.readyState === WebSocket.CONNECTING) {
                _socket.close(1000, "Client disconnected");
            }

            _socket = null;
        }

        _jobId = null;
        _onLogEntry = null;
        _onStatusUpdate = null;
        _onJobFinished = null;
        _onConnectionChange = null;
    }

    function isConnected() {
        return _socket !== null && _socket.readyState === WebSocket.OPEN;
    }

    function getJobId() {
        return _jobId;
    }


    // ---------------------------------------------------------------------------
    //    Internal
    function _createConnection() {
        var protocol = window.location.protocol === "https:" ? "wss:" : "ws:";
        var wsUrl = protocol + "//" + window.location.host + "/api/logs/ws/" + _jobId;

        _socket = new WebSocket(wsUrl);

        _socket.onopen = function () {
            _reconnectAttempts = 0;
            if (_onConnectionChange) {
                _onConnectionChange(true);
            }
        };

        _socket.onmessage = function (event) {
            var data;
            try {
                data = JSON.parse(event.data);
            } catch (e) {
                return;
            }

            // Route the message based on type
            if (data.type === "status_update") {
                if (_onStatusUpdate) {
                    _onStatusUpdate(data);
                }
            } else if (data.type === "job_finished") {
                if (_onJobFinished) {
                    _onJobFinished(data);
                }
                // Don't auto-reconnect after job finishes
                _maxReconnectAttempts = 0;
            } else {
                // Regular log entry
                if (_onLogEntry) {
                    _onLogEntry(data);
                }
            }
        };

        _socket.onclose = function (event) {
            if (_onConnectionChange) {
                _onConnectionChange(false);
            }

            // Attempt reconnect if not intentionally closed
            if (event.code !== 1000 && _reconnectAttempts < _maxReconnectAttempts && _jobId) {
                _reconnectAttempts++;
                var delay = _reconnectDelay * Math.min(_reconnectAttempts, 5);
                _reconnectTimer = setTimeout(function () {
                    if (_jobId) {
                        _createConnection();
                    }
                }, delay);
            }
        };

        _socket.onerror = function () {
            // onerror is always followed by onclose, so we handle reconnect there
        };
    }


    // ---------------------------------------------------------------------------
    //    Return public interface
    return {
        connect: connect,
        disconnect: disconnect,
        isConnected: isConnected,
        getJobId: getJobId,
    };

})();
