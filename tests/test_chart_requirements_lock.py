from pathlib import Path


def test_chart_lock_has_hashes_for_every_pinned_package() -> None:
    lines = Path('requirements-charts.lock').read_text(encoding='utf-8').splitlines()
    requirements = [
        (index, line.strip())
        for index, line in enumerate(lines)
        if line.strip() and not line.startswith(('#', ' ', '\t'))
    ]
    expected = {
        'aiodns', 'aiohappyeyeballs', 'aiohttp', 'aiosignal', 'annotated-types', 'attrs', 'backports.zstd',
        'brotli', 'cffi', 'frozenlist', 'idna', 'lunar-python', 'multidict', 'pminit', 'propcache',
        'py-iztro', 'pycares', 'pycparser', 'pydantic', 'pydantic-core', 'pyswisseph', 'pythonmonkey',
        'tzdata', 'typing-extensions', 'yarl',
    }
    assert {requirement.partition('==')[0].lower() for _, requirement in requirements} == expected
    assert len(requirements) == len(expected)
    assert len({requirement for _, requirement in requirements}) == len(requirements)
    for index, requirement in requirements:
        assert '==' in requirement
        following = lines[index + 1 :]
        hashes = []
        for line in following:
            stripped = line.strip()
            if not stripped.startswith('--hash=sha256:'):
                break
            digest = stripped.removeprefix('--hash=sha256:').removesuffix('\\').strip()
            assert len(digest) == 64 and set(digest) <= set('0123456789abcdef')
            hashes.append(digest)
        assert hashes, f'missing reviewed artifact hash: {requirement}'
