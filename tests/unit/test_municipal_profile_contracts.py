from __future__ import annotations

import re
from unittest.mock import Mock

import pytest
from bs4 import BeautifulSoup, Comment
from profile_cases import PROFILE_BATCHES, ProfileBatch, profile_cases

from judgefinder.adapters.sources.generic_engine.profiled_html import parse_profiled_html
from judgefinder.adapters.sources.generic_engine.profiled_json import parse_profiled_json
from judgefinder.domain.notice_classification import (
    NoticeCategory,
    classify_notice,
    classify_notice_title,
)


@pytest.mark.parametrize(
    ("batch", "slug"),
    [
        *profile_cases("busan_daegu_ten"),
        *profile_cases("busan_ten"),
        *profile_cases("seoul_busan_ten"),
    ],
)
def test_real_title_registration_date_and_official_detail(batch: ProfileBatch, slug: str) -> None:
    case = batch.cases[slug]
    source = batch.settings.sources[slug]
    assert source.html_profile is not None
    loader = Mock(return_value=case["detail_html"])
    actual = parse_profiled_html(
        case["list_html"],
        list_url=source.list_url,
        profile=source.html_profile,
        detail_loader=loader,
    )
    assert [(n.title, str(n.published_date), n.url) for n in actual] == [
        (case["title"], case["date"], case["url"]),
    ]
    loader.assert_called_once_with(case["url"])
    assert classify_notice_title(actual[0].title) is NoticeCategory.RECRUITMENT


@pytest.mark.parametrize(
    ("batch", "slug"),
    [
        *profile_cases("busan_daegu_ten"),
        *profile_cases("busan_ten"),
    ],
)
def test_http_200_error_document_is_not_a_valid_detail(batch: ProfileBatch, slug: str) -> None:
    source = batch.settings.sources[slug]
    assert source.html_profile is not None
    with pytest.raises(ValueError, match="title or registration-date element missing"):
        parse_profiled_html(
            batch.cases[slug]["list_html"],
            list_url=source.list_url,
            profile=source.html_profile,
            detail_loader=Mock(return_value="<h2>Web firewall security policies: blocked.</h2>"),
        )


@pytest.mark.parametrize(
    ("batch", "title"),
    [
        *profile_cases(
            "busan_ten",
            [
                "제안서 평가위원회 개최 일정 변경 공고",
                "제안서 평가위원회 위원별 점수 공개",
                "제안서 평가위원(후보자) 모집 취소 공고",
                "제안서 평가위원회 평가 결과 공개",
            ],
        ),
        *profile_cases(
            "seoul_busan_ten",
            [
                "제안서 평가위원회 평가결과 공개",
                "제안서 평가위원(후보자) 모집 취소 공고",
                "제안서 평가위원회 구성 결과 알림",
            ],
        ),
        *profile_cases(
            "seoul_ten",
            [
                "홍제역 역세권활성화사업 분야별 용역 제안서평가위원(후보자) 모집 취소 공고",
                "제안서평가위원회[2025-2026 동대문구 눈썰매장] 결과 공고",
                "2026~27년 U-양천 통합관제센터 및 CCTV 유지보수 평가위원별 점수공개",
                "2026년 상반기 마포구 성별영향평가위원회 서면심의 결과",
                "2025년 하반기 마포구 성별영향평가위원회 서면심의 결과",
            ],
        ),
    ],
)
def test_results_cancellations_and_schedule_changes_are_not_recruitment(
    batch: ProfileBatch, title: str
) -> None:
    assert classify_notice_title(title) is not NoticeCategory.RECRUITMENT


@pytest.mark.parametrize(
    ("batch", "slug"),
    [
        *profile_cases("chungbuk_chungnam_jeonbuk_thirty", lambda batch: batch.recovered),
        *profile_cases("jeonbuk_gyeongbuk_gyeongnam_thirty", lambda batch: batch.recovered),
    ],
)
def test_actual_recovered_notice_retains_original_title_date_and_url(
    batch: ProfileBatch, slug: str
) -> None:
    source, case = batch.settings.sources[slug], batch.recovered[slug]
    actual = parse_profiled_html(
        case["list_html"],
        list_url=source.list_url,
        profile=source.html_profile,
        detail_loader=Mock(return_value=case["detail_html"]),
        recruitment_only=True,
    )
    assert [(n.title, str(n.published_date), n.url) for n in actual] == [
        (case["title"], case["date"], case["url"]),
    ]
    assert classify_notice(actual[0].title, actual[0].body_text) is NoticeCategory.RECRUITMENT


@pytest.mark.parametrize(
    "batch",
    [
        pytest.param(
            PROFILE_BATCHES["chungbuk_chungnam_jeonbuk_thirty"],
            id="chungbuk_chungnam_jeonbuk_thirty",
        ),
        pytest.param(
            PROFILE_BATCHES["jeonbuk_gyeongbuk_gyeongnam_thirty"],
            id="jeonbuk_gyeongbuk_gyeongnam_thirty",
        ),
    ],
)
def test_recovered_fixtures_do_not_include_contact_values_or_scripts(batch: ProfileBatch) -> None:
    for case in batch.recovered.values():
        soup = BeautifulSoup(case["detail_html"], "html5lib")
        assert not soup.select("script,style,input,iframe")
        assert not re.search(r"[\w.+-]+@[\w.-]+|\b0\d{1,2}-\d{3,4}-\d{4}\b", soup.get_text())


@pytest.mark.parametrize(
    ("batch", "slug"),
    [
        *profile_cases("chungbuk_chungnam_jeonbuk_thirty"),
        *profile_cases("gyeonggi_gangwon_chungbuk_thirty"),
        *profile_cases("jeonbuk_gyeongbuk_gyeongnam_thirty"),
    ],
)
def test_actual_title_display_date_and_stable_official_url(batch: ProfileBatch, slug: str) -> None:
    source, case = batch.settings.sources[slug], batch.cases[slug]
    if source.json_profile:
        actual = parse_profiled_json(
            case["list_json"],
            list_url=source.list_url,
            profile=source.json_profile,
            expected_page=1,
        )
    else:
        assert source.html_profile is not None
        loader = Mock(return_value=case["detail_html"])
        actual = parse_profiled_html(
            case["list_html"],
            list_url=source.list_url,
            profile=source.html_profile,
            detail_loader=loader,
            expected_page=1,
            recruitment_only=True,
        )
        loader.assert_called_once_with(case["url"])
    assert [(n.title, str(n.published_date), n.url) for n in actual] == [
        (case["title"], case["date"], case["url"]),
    ]


@pytest.mark.parametrize(
    ("batch", "slug"),
    [
        *profile_cases(
            "chungbuk_chungnam_jeonbuk_thirty",
            lambda batch: [
                slug for slug, source in batch.settings.sources.items() if source.html_profile
            ],
        ),
        *profile_cases(
            "daejeon_ulsan_sejong_gyeonggi_ten",
            lambda batch: [
                s for s in batch.settings.enabled_sources if batch.settings.sources[s].html_profile
            ],
        ),
        *profile_cases(
            "gyeonggi_cities_next_ten",
            lambda batch: [s for s, c in batch.cases.items() if not c["listing_only"]],
        ),
        *profile_cases(
            "gyeonggi_cities_ten",
            lambda batch: [s for s, c in batch.cases.items() if not c["listing_only"]],
        ),
        *profile_cases(
            "gyeonggi_gangwon_chungbuk_thirty",
            lambda batch: [
                slug for slug, source in batch.settings.sources.items() if source.html_profile
            ],
        ),
        *profile_cases(
            "jeonbuk_gyeongbuk_gyeongnam_thirty",
            lambda batch: [
                slug for slug, source in batch.settings.sources.items() if source.html_profile
            ],
        ),
        *profile_cases("jeonnam_daejeon_ten"),
    ],
)
def test_missing_detail_title_is_a_failure_not_successful_zero(
    batch: ProfileBatch, slug: str
) -> None:
    source = batch.settings.sources[slug]
    assert source.html_profile is not None
    with pytest.raises(ValueError, match="title or registration-date element missing"):
        parse_profiled_html(
            batch.cases[slug]["list_html"],
            list_url=source.list_url,
            profile=source.html_profile,
            detail_loader=Mock(return_value="<h1>Error</h1>"),
        )


@pytest.mark.parametrize(
    ("batch", "slug"),
    [
        *profile_cases(
            "chungbuk_chungnam_jeonbuk_thirty",
            lambda batch: [
                slug for slug, source in batch.settings.sources.items() if source.html_profile
            ],
        ),
        *profile_cases(
            "gyeonggi_gangwon_chungbuk_thirty",
            lambda batch: [
                slug for slug, source in batch.settings.sources.items() if source.html_profile
            ],
        ),
        *profile_cases(
            "jeonbuk_gyeongbuk_gyeongnam_thirty",
            lambda batch: [
                slug for slug, source in batch.settings.sources.items() if source.html_profile
            ],
        ),
    ],
)
def test_broken_official_listing_fails_closed(batch: ProfileBatch, slug: str) -> None:
    source = batch.settings.sources[slug]
    assert source.html_profile is not None
    with pytest.raises(ValueError, match="HTML listing container missing"):
        parse_profiled_html(
            "<h1>Forbidden</h1>",
            list_url=source.list_url,
            profile=source.html_profile,
            expected_page=1,
        )


@pytest.mark.parametrize(
    ("batch", "slug"),
    [
        *profile_cases(
            "chungbuk_chungnam_jeonbuk_thirty",
            lambda batch: [
                slug
                for slug in [
                    slug for slug, source in batch.settings.sources.items() if source.html_profile
                ]
                if batch.settings.sources[slug].html_profile.page_number_selector
            ],
        ),
        *profile_cases("daejeon_ulsan_sejong_gyeonggi_ten", ["ulsan", "ulju", "suwon"]),
        *profile_cases(
            "gyeonggi_cities_next_ten",
            lambda batch: [
                s
                for s, source in batch.settings.sources.items()
                if source.html_profile is not None and source.html_profile.page_number_selector
            ],
        ),
        *profile_cases(
            "gyeonggi_cities_ten",
            lambda batch: [
                s
                for s, source in batch.settings.sources.items()
                if source.html_profile is not None and source.html_profile.page_number_selector
            ],
        ),
        *profile_cases(
            "gyeonggi_gangwon_chungbuk_thirty",
            lambda batch: [
                slug
                for slug in [
                    slug for slug, source in batch.settings.sources.items() if source.html_profile
                ]
                if batch.settings.sources[slug].html_profile.page_number_selector
            ],
        ),
        *profile_cases(
            "jeonbuk_gyeongbuk_gyeongnam_thirty",
            lambda batch: [
                slug
                for slug in [
                    slug for slug, source in batch.settings.sources.items() if source.html_profile
                ]
                if batch.settings.sources[slug].html_profile.page_number_selector
            ],
        ),
        *profile_cases(
            "jeonnam_daejeon_ten",
            ["yeonggwang", "jangseong", "wando", "jindo", "shinan", "daejeon", "daejeon_seogu"],
        ),
    ],
)
def test_ignored_page_number_fails_before_loading_details(batch: ProfileBatch, slug: str) -> None:
    source = batch.settings.sources[slug]
    assert source.html_profile is not None
    loader = Mock()
    with pytest.raises(ValueError, match="page does not match"):
        parse_profiled_html(
            batch.cases[slug]["list_html"],
            list_url=source.list_url,
            profile=source.html_profile,
            detail_loader=loader,
            expected_page=2,
        )
    loader.assert_not_called()


@pytest.mark.parametrize(
    "batch",
    [
        pytest.param(
            PROFILE_BATCHES["chungbuk_chungnam_jeonbuk_thirty"],
            id="chungbuk_chungnam_jeonbuk_thirty",
        ),
        pytest.param(
            PROFILE_BATCHES["gyeonggi_gangwon_chungbuk_thirty"],
            id="gyeonggi_gangwon_chungbuk_thirty",
        ),
        pytest.param(
            PROFILE_BATCHES["jeonbuk_gyeongbuk_gyeongnam_thirty"],
            id="jeonbuk_gyeongbuk_gyeongnam_thirty",
        ),
    ],
)
def test_actual_fixtures_do_not_include_contact_metadata_or_remote_scripts(
    batch: ProfileBatch,
) -> None:
    for case in batch.cases.values():
        for key in ("list_html", "detail_html"):
            if key not in case:
                continue
            soup = BeautifulSoup(case[key], "html5lib")
            assert not soup.select("script,style,input,iframe")
            assert not soup.find_all(string=lambda n: isinstance(n, Comment))
            assert all(s not in soup.get_text() for s in ("담당자", "연락처", "전화번호"))


@pytest.mark.parametrize(
    ("batch", "slug"),
    [
        *profile_cases("daegu_incheon_ten"),
        *profile_cases("incheon_jeonnam_ten"),
    ],
)
def test_invalid_listing_is_not_treated_as_proof_of_zero_notices(
    batch: ProfileBatch, slug: str
) -> None:
    source = batch.settings.sources[slug]
    assert source.html_profile is not None
    with pytest.raises(ValueError, match="HTML listing container missing"):
        parse_profiled_html(
            "<h2>Service unavailable</h2>",
            list_url=source.list_url,
            profile=source.html_profile,
        )


@pytest.mark.parametrize(
    ("batch", "slug"),
    [
        *profile_cases(
            "daejeon_ulsan_sejong_gyeonggi_ten",
            lambda batch: [
                s for s in batch.settings.enabled_sources if batch.settings.sources[s].html_profile
            ],
        ),
        *profile_cases("gyeonggi_cities_next_ten"),
        *profile_cases("gyeonggi_cities_ten"),
        *profile_cases("jeonnam_daejeon_ten"),
    ],
)
def test_error_document_is_not_successful_zero(batch: ProfileBatch, slug: str) -> None:
    source = batch.settings.sources[slug]
    assert source.html_profile is not None
    with pytest.raises(ValueError, match="HTML listing container missing"):
        parse_profiled_html(
            "<h1>FORBIDDEN</h1>",
            list_url=source.list_url,
            profile=source.html_profile,
            expected_page=1,
        )


@pytest.mark.parametrize(
    ("batch", "slug"),
    [
        *profile_cases("gyeonggi_cities_next_ten"),
        *profile_cases("gyeonggi_cities_ten"),
    ],
)
def test_actual_full_title_date_and_canonical_notice_url(batch: ProfileBatch, slug: str) -> None:
    source, case = batch.settings.sources[slug], batch.cases[slug]
    assert source.html_profile is not None
    loader = Mock(return_value=case.get("detail_html", ""))
    actual = parse_profiled_html(
        case["list_html"],
        list_url=source.list_url,
        profile=source.html_profile,
        detail_loader=loader,
        expected_page=1,
        recruitment_only=case["listing_only"],
    )
    assert [(n.title, str(n.published_date), n.url) for n in actual] == [
        (case["title"], case["date"], case["url"]),
    ]
    if case["listing_only"]:
        assert case["category"] == "result"
        loader.assert_not_called()
    else:
        assert case["category"] == "recruitment"
        loader.assert_called_once_with(case["url"])


@pytest.mark.parametrize(
    "batch",
    [
        pytest.param(PROFILE_BATCHES["gyeonggi_cities_next_ten"], id="gyeonggi_cities_next_ten"),
        pytest.param(PROFILE_BATCHES["gyeonggi_cities_ten"], id="gyeonggi_cities_ten"),
    ],
)
def test_real_response_fixtures_are_sanitized(batch: ProfileBatch) -> None:
    for case in batch.cases.values():
        for key in ("list_html", "detail_html"):
            if key not in case:
                continue
            soup = BeautifulSoup(case[key], "html.parser")
            assert not soup.select("script,style,input,iframe")
            assert not soup.find_all(string=lambda n: isinstance(n, Comment))
            assert all(s not in soup.get_text() for s in ("담당자", "연락처", "전화번호"))


@pytest.mark.parametrize(
    ("batch", "slug"),
    [
        *profile_cases(
            "jeonnam_counties_ten",
            lambda batch: [slug for slug, case in batch.cases.items() if "detail_html" in case],
        ),
        *profile_cases(
            "jeonnam_gwangju_ten",
            lambda batch: [slug for slug, case in batch.cases.items() if "detail_html" in case],
        ),
    ],
)
def test_error_document_is_not_an_authoritative_detail(batch: ProfileBatch, slug: str) -> None:
    source = batch.settings.sources[slug]
    assert source.html_profile is not None
    with pytest.raises(ValueError, match="title or registration-date element missing"):
        parse_profiled_html(
            batch.cases[slug]["list_html"],
            list_url=source.list_url,
            profile=source.html_profile,
            detail_loader=Mock(return_value="<h1>Service error</h1>"),
        )
