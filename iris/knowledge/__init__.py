"""Wiki·코드 인덱스·가져오기.

Agent-readable:
- Owns: Iris Wiki, Obsidian 볼트, 코드 인덱스, 요약 저장.
- Does not: 벡터 RAG(미구현), Hermes 웹 검색.
- Talks to: `iris/storage`, Wiki UI.
- Extend via: 저장은 이 패키지. Hermes에서 부르려면 `iris/ui/control_actions/wiki.py`.
"""
