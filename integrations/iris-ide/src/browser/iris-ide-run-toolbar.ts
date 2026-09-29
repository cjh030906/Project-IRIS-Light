import { inject, injectable } from '@theia/core/shared/inversify';
import { codicon, Widget } from '@theia/core/lib/browser';
import { TabBarToolbarContribution, TabBarToolbarRegistry } from '@theia/core/lib/browser/shell/tab-bar-toolbar';
import { Command, CommandContribution, CommandRegistry, MenuContribution, MenuModelRegistry } from '@theia/core/lib/common';
import { FileUri } from '@theia/core/lib/common/file-uri';
import { EditorWidget } from '@theia/editor/lib/browser';

import { IrisIdeBridgePoller } from './iris-ide-bridge-poller';

/** Theia가 editor/title/run 이 비어 있으면 'Run or Debug...' 버튼 자체를 그리지 않는다. */
const EDITOR_TITLE_RUN_MENU = ['plugin_editor/title/run'];

export namespace IrisIdeRunCommands {
    export const RUN_FILE: Command = {
        id: 'iris.ide.runFile',
        label: 'Run File',
    };
}

const RUNNERS: Record<string, string> = {
    py: 'python',
    pyw: 'python',
    js: 'node',
    mjs: 'node',
    cjs: 'node',
};

function argvFor(absPath: string): string[] {
    const ext = absPath.replace(/\\/g, '/').split('.').pop()?.toLowerCase() ?? '';
    const bin = RUNNERS[ext];
    return bin ? [bin, absPath] : [absPath];
}

@injectable()
export class IrisIdeRunToolbar implements CommandContribution, MenuContribution, TabBarToolbarContribution {

    @inject(IrisIdeBridgePoller) protected readonly poller: IrisIdeBridgePoller;

    registerCommands(commands: CommandRegistry): void {
        commands.registerCommand(IrisIdeRunCommands.RUN_FILE, {
            execute: widget => this.runFile(widget),
            isEnabled: widget => this.fileOf(widget) !== undefined,
            isVisible: widget => widget instanceof EditorWidget,
        });
    }

    registerMenus(menus: MenuModelRegistry): void {
        menus.registerMenuAction(EDITOR_TITLE_RUN_MENU, {
            commandId: IrisIdeRunCommands.RUN_FILE.id,
            label: IrisIdeRunCommands.RUN_FILE.label,
            order: '0',
        });
    }

    registerToolbarItems(registry: TabBarToolbarRegistry): void {
        const onEditor = (widget: Widget): boolean => widget instanceof EditorWidget;
        registry.registerItem({
            id: IrisIdeRunCommands.RUN_FILE.id,
            command: IrisIdeRunCommands.RUN_FILE.id,
            icon: codicon('play'),
            tooltip: 'Run File',
            group: 'navigation',
            priority: 0,
            isVisible: onEditor,
        });
        registry.registerItem({
            id: 'iris.ide.splitEditorRight',
            command: 'workbench.action.splitEditorRight',
            icon: codicon('split-horizontal'),
            tooltip: 'Split Editor Right',
            group: 'navigation',
            priority: 1,
            isVisible: onEditor,
        });
    }

    protected fileOf(widget: unknown): string | undefined {
        if (!(widget instanceof EditorWidget)) {
            return undefined;
        }
        const uri = widget.editor?.uri;
        if (!uri) {
            return undefined;
        }
        return FileUri.fsPath(uri);
    }

    protected async runFile(widget: Widget | undefined): Promise<void> {
        const abs = this.fileOf(widget);
        if (!abs) {
            return;
        }
        const cwd = abs.replace(/[\\/][^\\/]*$/, '');
        await this.poller.runArgv(argvFor(abs), cwd);
    }
}
