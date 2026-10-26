# 🏗️ 설계서

- **담당:** 황웅재
- **평가 항목:** 아키텍처 설계 (2점)
- **필수 범위:** 3. 컴포넌트 설계까지 (설계서 템플릿이 LMS에 있으면 그 목차를 따름)
- **문서:** [설계서_찰칵부산_v1.0.md](설계서_찰칵부산_v1.0.md) (3장까지), [설계서_찰칵부산_v1.1.docx](설계서_찰칵부산_v1.1.docx) (SDD 템플릿 1~12장 전체, 제출본과 동일)

## 다이어그램

| 다이어그램 | 그림 | 원본 코드 | 설계서 v1.1 |
|---|---|---|---|
| 전체 구조 (계층) | [overall-structure.png](overall-structure.png) | [overall-structure.mmd](overall-structure.mmd) (Mermaid) | 그림 2-1 |
| 컴포넌트 | [component-diagram.png](component-diagram.png) | [component-diagram.puml](component-diagram.puml) | 그림 3-1 |
| 클래스 | [class-diagram.png](class-diagram.png) | [class-diagram.dot](class-diagram.dot) (Graphviz) | 그림 4-1 |
| 시퀀스 SD-01 사진 분석 (UC-01, UC-02) | [sequence-diagram.png](sequence-diagram.png) | [sequence-diagram.puml](sequence-diagram.puml) | 그림 4-2 |
| 시퀀스 SD-02 여행기 생성 (UC-06, UC-09) | [sequence-diagram-2.png](sequence-diagram-2.png) | [sequence-diagram-2.puml](sequence-diagram-2.puml) | 그림 4-3 |
| 방문지 상태 (DR-02) | [state-diagram.png](state-diagram.png) | [state-diagram.puml](state-diagram.puml) | 그림 4-4 |
| 배포 (Docker Compose) | [deployment-diagram.png](deployment-diagram.png) | [deployment-diagram.puml](deployment-diagram.puml) | 그림 10-1 |

- 그림은 설계서에 들어간 것과 같은 파일이다 (Visual Paradigm 무료판 워터마크 없는 버전)
- 클래스 다이어그램은 Graphviz로 렌더링: `dot -Tpng -Gdpi=200 class-diagram.dot -o class-diagram.png`
- SD-02 그림은 PlantUML이 없는 환경에서 puml 내용을 그대로 그린 것이다. PlantUML이나 VPasCode로 다시 렌더링하면 다른 시퀀스 그림과 모양이 맞는다

## 할 일

- [x] 아키텍처 스타일 선정과 근거 (초안 2.3)
- [x] 전체 구조도 (초안 2.4, Mermaid)
- [x] 품질 속성 (초안 2.2)
- [x] 컴포넌트 식별, 책임, 제공/요구 인터페이스, 의존관계 (초안 3장)
- [x] 컴포넌트 다이어그램 → [component-diagram.png](component-diagram.png) (원본 [component-diagram.puml](component-diagram.puml). v0.1은 Visual Paradigm VPasCode로, v1.0은 VLM 추론 서버·LLM API를 반영해 PlantUML로 다시 렌더링)
- [x] 사진 분석 시퀀스 다이어그램 (UC-01, UC-02) → [sequence-diagram.png](sequence-diagram.png) (원본 [sequence-diagram.puml](sequence-diagram.puml))
- [x] 방문지 상태 다이어그램 (DR-02) → [state-diagram.png](state-diagram.png) (원본 [state-diagram.puml](state-diagram.puml))
- [x] 배포 다이어그램 (Docker Compose) → [deployment-diagram.png](deployment-diagram.png) (원본 [deployment-diagram.puml](deployment-diagram.puml))
  - 제출본(docx·pdf)에는 위 3개 puml 원본을 PlantUML로 렌더링한 그림 사용 (Visual Paradigm 무료판 워터마크 제외)
- [x] 정합성 검토 결과(v0.2 부록 B) 정리 → 요구사항분석서 v0.2에 반영 (이슈 #5)
- [x] 팀 검토 반영 후 v1.0: 3장 컴포넌트 설계까지 9쪽으로 정리 (부록은 제출본에서 뺌, 이력은 git)
- [x] v1.1: SDD 템플릿(02_설계서(SDD)_템플릿.docx) 양식으로 이관, 4~12장(UML, 데이터, API, AI, 예외, 보안, 배포, 패턴, 추적표) 작성, 클래스·SD-02 다이어그램 추가 → 제출본 [../submission](../submission/)
