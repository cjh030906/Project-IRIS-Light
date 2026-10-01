/** Stub optional/unused native modules when node-gyp / VS C++ is missing (localhost browser Theia). */
const fs = require('fs');
const path = require('path');

const root = path.join(__dirname, '..', 'node_modules');

function stubWindowsCaCerts() {
    const dir = path.join(root, '@vscode', 'windows-ca-certs');
    const release = path.join(dir, 'build', 'Release');
    fs.rmSync(dir, { recursive: true, force: true });
    fs.mkdirSync(release, { recursive: true });
    fs.writeFileSync(
        path.join(dir, 'package.json'),
        JSON.stringify({ name: '@vscode/windows-ca-certs', version: '0.0.0-stub', main: 'index.js' }, null, 2),
        'utf8'
    );
    fs.writeFileSync(
        path.join(dir, 'index.js'),
        "'use strict';\nmodule.exports = { load: async () => undefined, getWindowsCaCerts: async () => [] };\n",
        'utf8'
    );
    // ponytail: esbuild only needs the path to exist for bundle — runtime uses stub JS
    fs.writeFileSync(path.join(release, 'crypt32.node'), Buffer.alloc(0));
    console.log('[iris-ide] stubbed @vscode/windows-ca-certs');
}

function neutralizeTheiaFfmpeg() {
    // resolutions should already point at vendor/theia-ffmpeg-stub; if the real
    // package landed somehow, drop binding.gyp so a later yarn/npm rebuild won't
    // require Visual Studio Desktop C++.
    const dir = path.join(root, '@theia', 'ffmpeg');
    if (!fs.existsSync(dir)) {
        return;
    }
    const binding = path.join(dir, 'binding.gyp');
    if (fs.existsSync(binding)) {
        fs.unlinkSync(binding);
        console.log('[iris-ide] removed @theia/ffmpeg binding.gyp (native rebuild disabled)');
    }
    const pkgPath = path.join(dir, 'package.json');
    try {
        const pkg = JSON.parse(fs.readFileSync(pkgPath, 'utf8'));
        if (String(pkg.version || '').includes('iris-stub')) {
            console.log('[iris-ide] @theia/ffmpeg already stub resolution');
            return;
        }
    } catch (_err) {
        /* ignore */
    }
}

function neutralizeDrivelist() {
    const dir = path.join(root, 'drivelist');
    const pkgPath = path.join(dir, 'package.json');
    if (!fs.existsSync(pkgPath)) {
        return;
    }
    let pkg;
    try {
        pkg = JSON.parse(fs.readFileSync(pkgPath, 'utf8'));
    } catch (_err) {
        return;
    }
    if (String(pkg.version || '').includes('iris-stub')) {
        const release = path.join(dir, 'build', 'Release');
        fs.mkdirSync(release, { recursive: true });
        const nodeFile = path.join(release, 'drivelist.node');
        if (!fs.existsSync(nodeFile)) {
            fs.writeFileSync(nodeFile, Buffer.alloc(0));
        }
        console.log('[iris-ide] drivelist already stub resolution');
        return;
    }
    const stubMain = path.join(__dirname, '..', 'vendor', 'drivelist-stub', 'js', 'index.js');
    const destJs = path.join(dir, 'js', 'index.js');
    fs.mkdirSync(path.dirname(destJs), { recursive: true });
    fs.copyFileSync(stubMain, destJs);
    const binding = path.join(dir, 'binding.gyp');
    if (fs.existsSync(binding)) {
        fs.unlinkSync(binding);
    }
    pkg.main = 'js/index.js';
    pkg.scripts = Object.assign({}, pkg.scripts, { install: 'node -e "process.exit(0)"' });
    delete pkg.gypfile;
    fs.writeFileSync(pkgPath, JSON.stringify(pkg, null, 2), 'utf8');
    const release = path.join(dir, 'build', 'Release');
    fs.mkdirSync(release, { recursive: true });
    const nodeFile = path.join(release, 'drivelist.node');
    if (!fs.existsSync(nodeFile)) {
        fs.writeFileSync(nodeFile, Buffer.alloc(0));
    }
    console.log('[iris-ide] neutralized drivelist native build');
}

try {
    stubWindowsCaCerts();
    neutralizeTheiaFfmpeg();
    neutralizeDrivelist();
} catch (err) {
    console.warn('[iris-ide] native stub skipped:', err.message);
}
