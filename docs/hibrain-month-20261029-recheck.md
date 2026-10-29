# 하이브레인 최근 한 달 현재 수집기 재대조

검토일: 2026-10-29. 코드 기준: `8602b02`. 운영 코드·설정·운영 DB는 변경하지 않았다.

## 범위와 결론

기준은 **2026-09-29~2026-10-29(양 끝 포함)** 하이브레인 최초 등록일이다.
[평가심사 공개 목록](https://www.hibrain.net/research/researches/34/recruitments/425/recruits?listType=ING)의 진행·마감 공고 중, 공백을 제외한 제목에 `평가위원`이 포함된 글을 대상으로 했다.
일반 채용·다른 종류의 위원 모집과 현재 접수 가능 여부의 검증은 포함하지 않는다.

**확정 비교 표본 230건 중 대응 수집 197건(85.7%)**이다.
엄격한 원문 식별자 일치는 161건(70.0%)이고, 나머지 36건은 기존 기관·사업명 검수의 대응 원문을 이번에 재수집한 것이다.
기관·사업명 대응을 동일 게시물 번호의 증명으로 합치지 않았다. 제목 유사도만으로 성공을 확정하지 않았다.

| 대조 결과 | 건수 |
|---|---:|
| 원문 식별자 일치 | 161 |
| 기존 기관·사업명 검수 대응 재수집 | 36 |
| 후속 상태 공고만 확인, 동일 모집 성공에서 제외 | 2 |
| 이번 실수집 미확보, 수집 경로 오류 포함 | 31 |
| 확정 비교 표본 합계 | 230 |

**이 비율은 최근 한 달 전체 공고의 확정 수집률이 아니라, 확인 가능한 비교 표본의 대응률이다.**

## 기준 목록의 완전성 제한

- 진행 목록 111건과 마감 목록 300건을 공개 화면에서 읽었고, 제목 조건에 맞는 후보는 296건이었다.
- 기존 대조표의 226건이 모두 현재 목록에도 존재함을 확인했다. 당일 추가된 4건은 상세 최초 등록일을 새로 확인해 230건으로 늘렸다.
- 상세 126건에서 최초 등록일 122건을 읽었다. 121건은 기간 내이고 1건은 9월 28일로 기간 밖이었다.
- 일부 마감 상세 4건에서 CloudFront 403을 확인했고, 연속 접근 제한 후 추가 상세 요청을 중단했다. 접근 제한 우회는 하지 않았다.
- 비교 표본 230건 중 121건의 최초 등록일은 이번 상세 조회, 109건은 기존 검수 기록을 사용했다. 109건을 모두 이번에 상세 재검증했다고 표현하지 않는다.
- 추가 후보 65건은 최초 등록일 미확정이므로 기간 밖이나 수집 실패로 단정하지 않았고 비율 계산에서 제외했다. 마감 목록 전체의 완전한 월간 모수도 미확정이다.
- 전체 후보 296건의 상태·URL·날짜·실제 수집 결과는 [대조 CSV](hibrain-month-20261029-recheck-coverage.csv)에서 확인할 수 있다.

## 실제 수집 조건

- 26개 배치 예제와 이 PC의 개인 운영 설정 7개 소스를 사용했다. 총 344개 소스 ID, 경로·설정이 다른 중복 ID를 분리한 346개 프로파일이다.
- 원기관 게시일은 하이브레인 게시일과 다르므로 **2026-09-22~10-29**를 조회했다. 기존 검수에서 대응된 원기관 날짜의 최솟값도 9월 22일이었다.
- 기존 SourceRegistry·수집기·파서를 그대로 사용했다. 활성 fixture는 없고 TLS 인증서 검증을 유지했다.
- 호스트별 요청을 직렬화하고 최대 6개 작업을 실행했다. 프로파일당 240초, 전체 1,200초의 검토 상한을 뒀으며 최종 실행에서 예산 초과로 제외된 경로는 없었다.
- 최종 실행은 346개 중 337개 프로파일이 전체 조회 범위를 오류 없이 처리했고, 9개에서 오류가 있었다. 0건인 경로를 공고 부재가 검증된 경로로 취급하지 않는다.
- 수집 결과는 중복 제거 후 **707건**이다. 평가결과·취소 등 비교 대상 밖 데이터가 포함될 수 있으며 707건 전부를 하이브레인 일치 건수로 사용하지 않았다.
- 별도 검증 DB에서 대응된 기록의 기관·제목·URL·등록일을 전건 확인했다. 동일 데이터를 다시 저장한 결과 **707→707건**으로 동일했다. 이는 DB 재저장 검증이며 네트워크 전체 재수집 2회를 뜻하지 않는다.

## 새로 확인한 당일 공고 4건

| 대상 | 실제 수집 소스 | 원기관 등록일 | 결과 |
|---|---|---|---|
| [울진군 왕피천공원사업소 왕피천공원 빙상장 설치 및 운영 용역 제안서 평가위원 모집](https://www.hibrain.net/research/researches/34/recruitments/425/categories/MJR/categories/ALL/recruits/3604049) | uljin_current | 2026-10-28 | 원문 식별자 일치 |
| [경상남도 산청군 정곡천 재해복구사업 외8개 사업 손실보상 지원용역 평가위원 모집](https://www.hibrain.net/research/researches/34/recruitments/425/categories/MJR/categories/ALL/recruits/3604048) | sancheong | 2026-10-29 | 원문 식별자 일치 |
| [전남광주통합특별시 서구 상무1동 행정복지센터 주변 하수관로 정비공사 공법선정위원회 평가위원 모집](https://www.hibrain.net/research/researches/34/recruitments/425/categories/MJR/categories/ALL/recruits/3604046) | gwangju_seogu_current | 2026-10-29 | 원문 식별자 일치 |
| [경상북도문화관광공사 경북나드리 홈페이지 리뉴얼 사업 제안서 평가위원 모집](https://www.hibrain.net/research/researches/34/recruitments/425/categories/MJR/categories/ALL/recruits/3604045) | gyeongbuk_tourism | 2026-10-28 | 원문 식별자 일치 |

4건 모두 현재 수집기로 원문을 확보했다. 울진·경북문화관광공사는 원기관 등록일이 10월 28일이고, 산청·광주 서구는 10월 29일이다.
이 차이를 날짜 오류로 처리하거나 하이브레인 날짜로 덮어쓰지 않았다.

## 기존 결과와의 차이

기존 기록은 226건 중 193건 대응이었다. 이번에는 새 4건을 모두 확보하고, 기존 보류였던 성북 스마트재단실·양산 구소석마을·강진청자축제 3건도 확보했다.
반면 기존 성공 표본 중 김해 2건과 속초 1건은 이번 환경에서 재현되지 않았다. 단순한 퍼센트 증감으로 수집기 개선·악화를 단정하지 않는다.
강진은 제공된 gosi 원문을 독립 요청해 HTTP 200·제목·게시물 ID 29230을 확인하고, 현재 수집된 old_gosi_new 경로와 대응시켰다.

## 수집 경로 오류

| 소스 | 이번 오류 |
|---|---|
| gimhae | HTTPError: 400 Client Error: Bad Request |
| sokcho | 이 환경에서 HTTPS 인증서 체인 검증 실패; 검증 우회하지 않음 |
| daejeon | ValueError: HTML row 2: title or registration-date element missing |
| seodaemun_gosi | ValueError: HTML listing container missing; absence of notices is unverified |
| suwon | ValueError: HTML listing page does not match requested page |
| ulsan_donggu | ValueError: HTML listing container missing; absence of notices is unverified |
| wando | ValueError: HTML row 1: title or registration-date element missing |
| yeosu | ValueError: HTML listing container missing; absence of notices is unverified |
| yeosu_current | ValueError: HTML listing container missing; absence of notices is unverified |

김해 HTTP 400과 속초 TLS 오류는 이 실행의 관측값이며, 기관 전체가 영구적으로 수집 불가하거나 원인이 수집기 코드에만 있다고 확정한 것은 아니다.

## 미확보 표본

아래는 같은 원문을 확보하지 못한 표본이다. 공개 목록 미노출·원문 접근 문제·경로 미등록·식별 불확실성이 섞여 있으므로 모두 파서 버그로 분류하지 않는다.

| 공고 | 원기관 링크 | 상태 |
|---|---|---|
| [속초시 하수처리사업소 도시침수대응사업 신기술·특허 공법선정위원회 평가위원 모집](https://www.hibrain.net/research/researches/34/recruitments/425/categories/MJR/categories/ALL/recruits/3603788) | [원기관](https://www.sokcho.go.kr/sc/portal/sokchonews/notification) | 수집 경로 오류로 미확보 |
| [김해시 새내기공무원 멘토링 운영 위탁용역 제안서 평가위원 모집](https://www.hibrain.net/research/researches/34/recruitments/425/categories/MJR/categories/ALL/recruits/3603717) | [원기관](https://www.gimhae.go.kr/03360/00023/00029.web?amode=view&not_ancmt_mgt_no=110775&section=01) | 수집 경로 오류로 미확보 |
| [인천광역시 제물포구 행정구역 조정 연구용역 제안서 평가위원 후보자 모집](https://www.hibrain.net/research/researches/34/recruitments/425/categories/MJR/categories/ALL/recruits/3603103) | [원기관](https://www.jemulpo.go.kr/main/bbs/bbsMsgDetail.do?bcd=notice&msg_seq=59881) | 이번 실수집 미확보 |
| [인천광역시 제물포구 박물관 소장품 DB 등록 용역 제안서 평가위원 모집](https://www.hibrain.net/research/researches/34/recruitments/425/categories/MJR/categories/ALL/recruits/3603040) | [원기관](https://www.jemulpo.go.kr/main/bbs/bbsMsgDetail.do?bcd=announce&msg_seq=14300) | 이번 실수집 미확보 |
| [평택시 공법선정위원회 평가위원 모집](https://www.hibrain.net/research/researches/34/recruitments/425/categories/MJR/categories/ALL/recruits/3602767) | [원기관](https://www.pyeongtaek.go.kr/pyeongtaek/saeol/gosi/view.do?notAncmtMgtNo=122614&mid=0401020100) | 이번 실수집 미확보 |
| [서울특별시 영등포구청 구내식당 운영 위탁업체 선정 제안서 평가위원 모집](https://www.hibrain.net/research/researches/34/recruitments/425/categories/MJR/categories/ALL/recruits/3602672) | [원기관](https://www.ydp.go.kr/www/selectEminwonView.do?key=2851&menuFlag=01&notAncmtMgtNo=39747) | 이번 실수집 미확보 |
| [부산광역시 국가유산 방문의 해 기획·종합운영 대행 용역 제안서 평가위원 모집](https://www.hibrain.net/research/researches/34/recruitments/425/categories/MJR/categories/ALL/recruits/3602665) | [원기관](https://www.busan.go.kr/nbgosi/view?curPage=1&gosiGbn=A&sno=79987) | 이번 실수집 미확보 |
| [부산광역시 제27회 전국생활체육대축전 및 제6회 전국장애인체생활체육대축전 개·폐회식 연출 및 행사운영 대행용역 제안서 평가위원 모집](https://www.hibrain.net/research/researches/34/recruitments/425/categories/MJR/categories/ALL/recruits/3602276) | [원기관](https://www.busan.go.kr/nbgosi/view?curPage=1&gosiGbn=A&sno=79950) | 이번 실수집 미확보 |
| [군포시 민원콜센터 정보통신시스템 유지관리 용역 제안서 평가위원 모집](https://www.hibrain.net/research/researches/34/recruitments/425/categories/MJR/categories/ALL/recruits/3602257) | [원기관](http://www.gunpo.go.kr/www/selectEminwonView.do?Not_ancmt_se_code=01&key=3907&notAncmtSeCd=01&not_ancmt_mgt_no=45844) | 이번 실수집 미확보 |
| [파주시 지하철 3호선 사업화방안 전략수립 연구용역 제안서 평가위원 모집](https://www.hibrain.net/research/researches/34/recruitments/425/categories/MJR/categories/ALL/recruits/3602067) | [원기관](https://www.paju.go.kr/user/board/BD_board.view.do?seq=20261014171913784&bbsCd=1022&q_ctgCd=4063&q_parentCtgCd=&pageType=&showSummaryYn=N&delDesc=&q_searchKeyType=&q_searchVal=&q_startDt=&q_endDt=&q_currPage=1&q_sortName=&q_sortOrder=&q_rowPerPage=10&q_chooseCnt=10&q_rowPerPage_row=10) | 이번 실수집 미확보 |
| [충청남도 2026 지방시대 엑스포 충청남도 전시관 설치·운영 용역 제안서 평가위원 모집](https://www.hibrain.net/research/researches/34/recruitments/425/categories/MJR/categories/ALL/recruits/3601922) | [원기관](https://www.chungnam.go.kr/cnportal/province/province/view.do?cl1CdValue=&menuNo=500487&nttId=2184552&pageIndex=1) | 이번 실수집 미확보 |
| [서울특별시 서울국제정원박람회 행사대행용역 제안서 평가위원 모집](https://www.hibrain.net/research/researches/34/recruitments/425/categories/MJR/categories/ALL/recruits/3601846) | [원기관](https://www.seoul.go.kr/news/news_employ.do?nttNo=468054) | 이번 실수집 미확보 |
| [경주시 동천 가동보 설치공사 가동보 공법 제안서 평가위원 모집](https://www.hibrain.net/research/researches/34/recruitments/425/categories/MJR/categories/ALL/recruits/3601765) | [원기관](https://www.gyeongju.go.kr/open_content/ko/page.do?mnu_uid=423&pageNo=1&pageOrder=0&pagePrvNxt=1&pageRef=0&parm_bod_uid=336870&parm_mnu_uid=0&srchBgpUid=-1&srchColumn=&srchEDate=9999-12-31&srchEnable=1&srchKeyword=&srchSDate=1960-01-01&srchVoteType=-1&step=258) | 이번 실수집 미확보 |
| [대구광역시 사회복지시설 종사자 처우 실태조사 및 개선방안 연구용역 제안서 평가위원회 평가위원 모집](https://www.hibrain.net/research/researches/34/recruitments/425/categories/MJR/categories/ALL/recruits/3601678) | [원기관](https://www.daegu.go.kr/index.do?menu_id=00940170) | 이번 실수집 미확보 |
| [경주시 불국사 사천왕 벽화 및 후불벽 배면 벽화 보존처리 용역 제안서 평가위원 모집](https://www.hibrain.net/research/researches/34/recruitments/425/categories/MJR/categories/ALL/recruits/3601669) | [원기관](https://www.gyeongju.go.kr/open_content/ko/page.do?mnu_uid=423&pageNo=1&pageOrder=0&pagePrvNxt=1&pageRef=0&parm_bod_uid=336852&parm_mnu_uid=0&srchBgpUid=-1&srchColumn=&srchEDate=9999-12-31&srchEnable=1&srchKeyword=&srchSDate=1960-01-01&srchVoteType=-1&step=258) | 이번 실수집 미확보 |
| [대구광역시 민방위 경보시설 유지보수 용역 제안서 평가위원 모집](https://www.hibrain.net/research/researches/34/recruitments/425/categories/MJR/categories/ALL/recruits/3601424) | [원기관](https://www.daegu.go.kr/index.do?menu_id=00940170) | 이번 실수집 미확보 |
| [대구광역시 도시건설본부 3공단지구 자연재해위험개선지구 정비사업 재난안전신기술 공법선정위원회 평가위원 모집](https://www.hibrain.net/research/researches/34/recruitments/425/categories/MJR/categories/ALL/recruits/3601423) | [원기관](https://www.daegu.go.kr/index.do?menu_id=00940170) | 이번 실수집 미확보 |
| [대구광역시 산업단지 입주업종 완화 연구용역 제안서 평가위원회 평가위원 모집](https://www.hibrain.net/research/researches/34/recruitments/425/categories/MJR/categories/ALL/recruits/3601135) | [원기관](https://www.daegu.go.kr/index.do?menu_id=00940170) | 이번 실수집 미확보 |
| [속초시 평화경제특구 전략환경영향평가 용역 제안서 평가위원 모집](https://www.hibrain.net/research/researches/34/recruitments/425/categories/MJR/categories/ALL/recruits/3601019) | [원기관](http://www.sokcho.go.kr/sc/portal/sokchonews/notification?notAncmtMgtNo=34405) | 이번 실수집 미확보 |
| [제천시 의림지뜰 자연치유단지 계류식 가스기구 제작·구매 및 설치 제안서 평가위원 모집](https://www.hibrain.net/research/researches/34/recruitments/425/categories/MJR/categories/ALL/recruits/3601017) | [원기관](https://www.jecheon.go.kr/www/selectBbsNttView.do?key=5233&id=&bbsNo=18&nttNo=404585&searchCtgry=&searchCnd=&searchKrwd=&pageIndex=2&integrDeptCode=) | 이번 실수집 미확보 |
| [인천광역시 제물포구 주민자치회 역량강화 워크숍 제안서 평가위원 모집](https://www.hibrain.net/research/researches/34/recruitments/425/categories/MJR/categories/ALL/recruits/3600963) | [원기관](https://www.jemulpo.go.kr/main/bbs/bbsMsgDetail.do?bcd=announce&msg_seq=14253) | 이번 실수집 미확보 |
| [속초시 속초시민 새해맞이 행사 행사대행용역 제안서 평가위원 모집](https://www.hibrain.net/research/researches/34/recruitments/425/categories/MJR/categories/ALL/recruits/3600828) | [원기관](http://www.sokcho.go.kr/sc/portal/sokchonews/notification?notAncmtMgtNo=34386) | 이번 실수집 미확보 |
| [태백시 맞춤형 복지제도 운영사 선정 제안서 평가위원 모집](https://www.hibrain.net/research/researches/34/recruitments/425/categories/MJR/categories/ALL/recruits/3600717) | [원기관](https://www.taebaek.go.kr/www/selectBbsNttView.do?bbsNo=25&integrDeptCode=&key=352&nttNo=185728&pageIndex=1&searchCnd=all&searchCtgry=&searchKrwd=) | 이번 실수집 미확보 |
| [한국산업안전보건공단 공공기관 안전활동 수준평가 위촉직 평가위원 모집](https://www.hibrain.net/research/researches/34/recruitments/425/categories/MJR/categories/ALL/recruits/3600277) | [원기관](https://portal.kosha.or.kr/business-apply-search/etc-biz/public-eval/biz-notic?bbsId=B2025111700003&pstNo=20261001101642WDDHMJ) | 이번 실수집 미확보 |
| [김해시 특정제품 선정 위원회 평가위원 모집](https://www.hibrain.net/research/researches/34/recruitments/425/categories/MJR/categories/ALL/recruits/3600235) | [원기관](https://www.gimhae.go.kr/03360/00023/00029.web?amode=view&not_ancmt_mgt_no=110267&section=01) | 수집 경로 오류로 미확보 |
| [경상남도 대한민국 지방시대 엑스포 경상남도 전시관 설치운영 용역 제안서 평가위원회 예비평가위원 모집](https://www.hibrain.net/research/researches/34/recruitments/425/categories/MJR/categories/ALL/recruits/3600163) | [원기관](https://www.gyeongnam.go.kr/index.gyeong?conGosiGbn=&conIfmEnddt=2026-09-30&conIfmStdt=2026-06-30&conTitle=&gosiGbn=A&menuCd=DOM_000000135003009001&mode=view&page=1&pageLine=10&searchCnt=&sno=55552) | 이번 실수집 미확보 |
| [부산광역시 2026 대한민국 지방시대 엑스포 부산시 전시관 설치·운영 용역 제안서 평가위원 모집](https://www.hibrain.net/research/researches/34/recruitments/425/categories/MJR/categories/ALL/recruits/3600071) | [원기관](https://www.busan.go.kr/nbgosi/view?curPage=1&gosiGbn=A&sno=79752) | 이번 실수집 미확보 |
| [하남시 도시교통정비 중기계획 등 종합교통계획 수립 용역 제안서 평가위원 모집](https://www.hibrain.net/research/researches/34/recruitments/425/categories/MJR/categories/ALL/recruits/3600068) | [원기관](https://www.hanam.go.kr/www/selectGosiData.do?key=171&not_ancmt_se_code=01%2C04&not_ancmt_mgt_no=52712) | 이번 실수집 미확보 |
| [안동시 상권활성화추진단 안동원도심상권 해외선진지 견학 및 벤치마킹 용역 제안서 평가위원 모집](https://www.hibrain.net/research/researches/34/recruitments/425/categories/MJR/categories/ALL/recruits/3600062) | [원기관](https://www.andong.go.kr/portal/bbs/list.do?mId=0401070000&ptIdx=76) | 이번 실수집 미확보 |
| [충청남도 지방상수도 유수율 효율화 통합모니터링 시스템 구축 감리용역 제안서 평가위원 모집](https://www.hibrain.net/research/researches/34/recruitments/425/categories/MJR/categories/ALL/recruits/3599961) | [원기관](https://www.chungnam.go.kr/cnportal/province/province/view.do?cl1CdValue=&menuNo=500487&nttId=2183847&pageIndex=1) | 이번 실수집 미확보 |
| [서울특별시 중구 간판개선사업 제안서 평가위원 모집](https://www.hibrain.net/research/researches/34/recruitments/425/categories/MJR/categories/ALL/recruits/3599868) | [원기관](http://www.junggu.seoul.kr/content.do?cid=1477245939&cmsid=14232&mode=view) | 이번 실수집 미확보 |

제물포 박물관 DB·주민자치회 워크숍은 새올에 같은 기관·사업명의 후보가 있지만 제공된 구청 원문은 이번 독립 요청에서 HTTP 400이었다. 서로 다른 게시물 ID의 연결을 확정하지 못해 위 성공 건수에서 제외했다.

## 다음 월간 검토 우선순위

1. 최초 등록일을 확인하지 못한 후보의 합법적인 공개 열람·사용자 내보내기 자료를 확보해 월간 비교 모수를 완성한다.
2. 김해의 공개 검색 요청 형식과 속초의 서버/실행 환경 인증서 체인을 확인해 기존 성공 3건의 재현성을 회복한다.
3. 제물포 등 다른 공식 게시판에 있는 동일사업 후보의 원문·모집기간·평가일을 추가 대조한다. 제목 유사도만으로 연결하지 않는다.
4. 안전보건공단 등의 미확보 표본은 공개 목록/API 형식과 원기관의 전체 이력 노출 범위를 확인한 뒤 경로 확장 대상으로 분류한다.
5. 다음 달에도 최초 등록일 기준 기간, 원문 식별자 일치, 기관·사업명 대응, 후속 공고, 미확보, 기간 미확정을 분리해 기록한다. 자동 예약은 생성하지 않았다.

## 검증 자료

원시 응답·브라우저 메타데이터·오류·검증 DB는 Git에서 제외되는 `data/live-tests/hibrain-month-20261029-recheck/`에 있다.
주요 파일: `browser-lists.json`, `browser-details.json`, `collection-results.json`, `comparison.json`, `notices.db`, `independent/checks.json`, `audit-final.json`.
현재 수집기 코드는 수정하지 않았고 새 수집 경로도 추가하지 않았다. 운영 설정·운영 DB·기존 검증 문서·커밋·push는 변경하지 않았다.
