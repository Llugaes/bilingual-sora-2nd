'use strict';
// Redirect only the unchanged legacy check's receipt, never its inputs/assertions.
const fs = require('node:fs');
const path = require('node:path');
const original = fs.writeFileSync;
const legacy = path.resolve('generated/r26-tools-header-regression.json');
const output = path.resolve('generated/r32-final-partitions-itemhelp-header.json');
fs.writeFileSync = function(filename, ...args) {
    return original.call(this, typeof filename === 'string' && path.resolve(filename) === legacy ? output : filename, ...args);
};
