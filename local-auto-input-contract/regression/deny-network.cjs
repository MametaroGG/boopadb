'use strict';
require('node:net').Socket.prototype.connect = function(){ throw new Error('OFFLINE_REGRESSION_NETWORK_DENIED'); };
require('node:dgram').Socket.prototype.send = function(){ throw new Error('OFFLINE_REGRESSION_NETWORK_DENIED'); };
