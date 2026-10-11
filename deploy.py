"""Read-only release manifest. Importing this module never opens a connection.

There is deliberately no automatic production apply path in this version. A
manifest is an inventory, not evidence that a release or migration was tested.
See README.md, "审阅发布步骤", before any separately reviewed deployment.
"""
import argparse
import hashlib
import json
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parent
APP_DESTINATION = '/root/mingjingtai'
SKILL_DESTINATION = '/root/.hermes/skills/zhiming'
STATIC_SUFFIXES = {'.js', '.cjs', '.css', '.html', '.svg', '.json'}
ROOT_FILES = (
    'main.py', 'zhiming-web.md', 'migration_state.py', 'deploy.py',
    'requirements.txt', 'requirements-web.lock', 'requirements-charts.lock',
    'package.json', 'package-lock.json', 'README.md', 'CHANGELOG-2026-10-10.md',
)
REQUIRED_FILES = ROOT_FILES + (
    'hermes/SKILL.md', 'hermes/state_store.py', 'hermes/tarot_store.py',
    'hermes/tarot_deck.py', 'static/index.html', 'static/app.js',
    'static/tarot/back.svg', 'static/tarot/licenses.json',
)


def _entry(root, path, destination, category):
    """Hash only regular files physically contained in the selected release."""
    relative = path.relative_to(root).as_posix()
    if path.is_symlink() or not path.resolve().is_relative_to(root):
        raise ValueError('发布文件不得是符号链接或指向目录外：' + relative)
    if not path.is_file():
        raise ValueError('发布文件不存在：' + relative)
    content = path.read_bytes()
    return {'source': relative, 'destination': destination, 'category': category,
            'bytes': len(content), 'sha256': hashlib.sha256(content).hexdigest()}


def build_manifest(release_dir=None):
    root = Path(release_dir).expanduser().resolve() if release_dir else ROOT
    if not root.is_dir():
        raise ValueError('release-dir 必须是存在的本地发布目录')
    for name in REQUIRED_FILES:
        if not (root / name).is_file():
            raise ValueError('发布目录缺少必需文件：' + name)
    for name in ('hermes', 'static', 'tests'):
        folder = root / name
        if folder.is_symlink() or (folder.exists() and not folder.resolve().is_relative_to(root)):
            raise ValueError('发布目录不得通过链接读取目录外文件：' + name)
    files = []
    for name in ROOT_FILES:
        files.append(_entry(root, root / name, APP_DESTINATION + '/' + name, 'application'))
    for path in sorted((root / 'hermes').rglob('*')):
        if path.is_file() and (path.suffix == '.py' or path.name == 'SKILL.md'):
            relative = path.relative_to(root / 'hermes').as_posix()
            files.append(_entry(root, path, SKILL_DESTINATION + '/' + relative, 'hermes'))
    for path in sorted((root / 'static').rglob('*')):
        if path.is_file() and path.suffix.lower() in STATIC_SUFFIXES:
            relative = path.relative_to(root).as_posix()
            files.append(_entry(root, path, APP_DESTINATION + '/' + relative, 'static'))
    if (root / 'tests').is_dir():
        for path in sorted((root / 'tests').rglob('*')):
            if path.is_file() and path.suffix.lower() in {'.py', '.cjs'}:
                relative = path.relative_to(root).as_posix()
                files.append(_entry(root, path, APP_DESTINATION + '/' + relative, 'verification'))
    inventory = json.dumps(files, ensure_ascii=False, sort_keys=True, separators=(',', ':'))
    return {'mode': 'dry-run', 'network_access': False, 'production_writes': False,
            'release_dir': str(root), 'release_verified': False,
            'notice': '仅本地文件清单；没有运行迁移、测试、上传、切换或重启服务。',
            'apply_supported': False, 'runbook': 'README.md#审阅发布步骤',
            'file_count': len(files), 'manifest_sha256': hashlib.sha256(inventory.encode()).hexdigest(),
            'files': files}


def main(argv=None):
    parser = argparse.ArgumentParser(description='默认只读本地发布清单；此版本禁止自动生产部署')
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument('--dry-run', action='store_true', help='只列文件、大小和 SHA256（默认）')
    mode.add_argument('--apply', action='store_true', help='受保护的拒绝入口；需按审阅 runbook 发布')
    parser.add_argument('--release-dir', help='本地隔离 stage 目录；仅指定目录不代表已经验证')
    parser.add_argument('--owner', help='迁移必须明确的数据归属；不接受隐式猜测')
    parser.add_argument('--bindings', help='迁移必须提供的受保护渠道绑定 JSON 路径；不会输出其内容')
    args = parser.parse_args(argv)
    if args.apply:
        missing = [name for name, value in (('--release-dir', args.release_dir),
                                            ('--owner', args.owner), ('--bindings', args.bindings)) if not value]
        if missing:
            parser.error('拒绝生产写入：缺少 ' + ', '.join(missing) + '。请按 README.md 的审阅发布步骤操作。')
        parser.error('拒绝自动 --apply：本版本没有经验证的备份/迁移/原子切换执行器。'
                     '请使用 README.md 的审阅发布步骤，先 .backup、迁移 dry-run/apply 核对数量，再审阅切换。')
    try:
        manifest = build_manifest(args.release_dir)
    except (OSError, ValueError) as exc:
        parser.error(str(exc))
    print(json.dumps(manifest, ensure_ascii=False, indent=2))
    return 0


if __name__ == '__main__':
    sys.exit(main())
