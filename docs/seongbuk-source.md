# Seongbuk District Open API Source

JudgeFinder supports the Seongbuk District public notice RSS API.

## Configuration

```toml
enabled_sources = ["seongbuk"]

[sources.seongbuk]
municipality = "성북구"
source_type = "api"
list_url = "https://www.sb.go.kr/www/gosiToRss.do"
# fixture_path = "tests/fixtures/seongbuk_rss.xml"
```

## Usage

```bash
judgefinder collect --date YYYY-MM-DD
judgefinder list --date YYYY-MM-DD
```

The Seongbuk adapter only returns notices for the requested date and filters for
evaluation-committee related keywords such as `제안서 평가위원` and `평가위원(후보자)`.
