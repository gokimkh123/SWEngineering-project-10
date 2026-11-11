"""컴포넌트 조립 (의존성 주입 지점).

설계서 3.3 의존 규칙에 맞춰 컴포넌트 인스턴스를 한 곳에서 만든다. 테스트에서는 어댑터(CP-18, CP-19)를
그대로 두고 장애 주입·응답 주입 속성만 바꿔 쓴다 (QA-08).
"""
from __future__ import annotations

from app.adapters.cp18_place_data import place_adapter
from app.adapters.cp19_ai_gateway import ai_gateway
from app.components.cp07_orchestrator import AnalysisOrchestrator
from app.components.cp10_candidates import CandidateFinder
from app.components.cp11_matcher import PlaceMatcher
from app.components.cp12_untagged import UntaggedPhotoResolver
from app.components.cp13_story import StoryGenerator
from app.components.cp15_repository import TripRepository
from app.components.cp16_place_cache import PlaceCache
from app.components.cp17_media_store import media_store

place_cache = PlaceCache(place_adapter)
repo = TripRepository(media_store)
finder = CandidateFinder(place_adapter, place_cache)
matcher = PlaceMatcher(ai_gateway)
resolver = UntaggedPhotoResolver(ai_gateway)
orchestrator = AnalysisOrchestrator(repo, media_store, place_cache, finder, matcher, resolver)
story_generator = StoryGenerator(ai_gateway, place_cache)
