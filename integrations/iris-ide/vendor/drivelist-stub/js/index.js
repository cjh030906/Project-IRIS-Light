'use strict';
/**
 * Browser-target stub for drivelist.
 * Theia only reads mountpoints[].path (EnvVariablesServerImpl.getDrives).
 * The real package runs prebuild-install || node-gyp and needs VS C++ on Windows.
 */
const fs = require('fs');

function winDrives() {
    const drives = [];
    for (let code = 65; code <= 90; code++) {
        const letter = String.fromCharCode(code);
        const root = letter + ':\\';
        try {
            fs.accessSync(root, fs.constants.R_OK);
        } catch (_err) {
            continue;
        }
        drives.push({
            device: root,
            displayName: letter + ':',
            description: 'Local Disk',
            size: null,
            mountpoints: [{ path: root }],
            isSystem: letter === 'C',
            isRemovable: false,
            isVirtual: false,
            isUSB: null,
            isReadOnly: false,
            raw: root,
        });
    }
    return drives;
}

function posixRoot() {
    return [{
        device: '/',
        displayName: '/',
        description: 'Local Disk',
        size: null,
        mountpoints: [{ path: '/' }],
        isSystem: true,
        isRemovable: false,
        isVirtual: false,
        isUSB: null,
        isReadOnly: false,
        raw: '/',
    }];
}

async function list() {
    if (process.platform === 'win32') {
        return winDrives();
    }
    return posixRoot();
}

module.exports = { list };
