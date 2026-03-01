# Municipal RSS Sources

JudgeFinder also supports several municipality RSS feeds that expose `고시/공고` notices.

## Configuration

```toml
enabled_sources = ["hanam", "pocheon", "cheorwon", "jecheon", "okcheon"]

[sources.hanam]
municipality = "하남시"
source_type = "api"
list_url = "https://www.hanam.go.kr/rssBbsNtt.do?bbsNo=31"

[sources.pocheon]
municipality = "포천시"
source_type = "api"
list_url = "https://www.pocheon.go.kr/www/selectEminwonList.do?key=12563&notAncmtSeCode=01"

[sources.cheorwon]
municipality = "철원군"
source_type = "api"
list_url = "https://www.cwg.go.kr/rssBbsNtt.do?bbsNo=25"

[sources.jecheon]
municipality = "제천시"
source_type = "api"
list_url = "https://www.jecheon.go.kr/rssBbsNtt.do?bbsNo=18"

[sources.okcheon]
municipality = "옥천군"
source_type = "api"
list_url = "https://www.oc.go.kr/rssBbsNtt.do?bbsNo=40"
```

Optional fixture paths can be set for deterministic local tests:

```toml
fixture_path = "tests/fixtures/hanam_rss.xml"
```

## Filter Behavior

- Notices are filtered by the requested `target_date`.
- Keyword filtering defaults to `평가위원` (title/description/content).

## Usage

```bash
judgefinder collect --date YYYY-MM-DD
judgefinder list --date YYYY-MM-DD
```
