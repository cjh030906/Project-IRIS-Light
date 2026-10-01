'use strict';
/**
 * Browser-target stub for @theia/ffmpeg.
 * Real package needs node-gyp + VS C++ (Electron codec tooling only).
 */
const path = require('path');

function _loadFfmpegNativeAddon() {
    return { codecs: () => [] };
}

function ffmpegNameAndLocation({ platform = process.platform } = {}) {
    switch (platform) {
        case 'darwin':
            return {
                name: 'libffmpeg.dylib',
                location:
                    'Electron.app/Contents/Frameworks/Electron Framework.framework/Libraries/',
            };
        case 'win32':
            return { name: 'ffmpeg.dll', location: '' };
        case 'linux':
            return { name: 'libffmpeg.so', location: '' };
        default:
            throw new Error(`${platform} is not supported`);
    }
}

function ffmpegRelativePath(options = {}) {
    const { location, name } = ffmpegNameAndLocation(options);
    return path.join(location, name);
}

function ffmpegAbsolutePath(options = {}) {
    return path.join(__dirname, 'stub-dist', ffmpegRelativePath(options));
}

function getFfmpegCodecs(_ffmpegPath) {
    return [];
}

async function checkFfmpeg(_options = {}) {
    return { free: [], proprietary: [] };
}

async function replaceFfmpeg(_options = {}) {
    return;
}

async function hashFile(_filePath) {
    return Buffer.alloc(32);
}

function readElectronVersion(_electronDist) {
    return Promise.resolve('0.0.0-stub');
}

module.exports = {
    _loadFfmpegNativeAddon,
    ffmpegNameAndLocation,
    ffmpegRelativePath,
    ffmpegAbsolutePath,
    getFfmpegCodecs,
    checkFfmpeg,
    replaceFfmpeg,
    hashFile,
    readElectronVersion,
    KNOWN_PROPRIETARY_CODECS: new Set(['h264', 'aac']),
};
