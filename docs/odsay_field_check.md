    ## 1. 응답 키 구조

```
searchType
outTrafficCheck
busCount
subwayCount
subwayBusCount
pointDistance
startRadius
endRadius
path
path[].pathType
path[].info
path[].info.trafficDistance
path[].info.totalWalk
path[].info.totalTime
path[].info.payment
path[].info.busTransitCount
path[].info.subwayTransitCount
path[].info.mapObj
path[].info.firstStartStation
path[].info.lastEndStation
path[].info.totalStationCount
path[].info.busStationCount
path[].info.subwayStationCount
path[].info.totalDistance
path[].info.totalWalkTime
path[].info.checkIntervalTime
path[].info.checkIntervalTimeOverYn
path[].info.totalIntervalTime
path[].subPath
path[].subPath[].trafficType
path[].subPath[].distance
path[].subPath[].sectionTime
path[].subPath[].stationCount
path[].subPath[].lane
path[].subPath[].lane[].busNo
path[].subPath[].lane[].type
path[].subPath[].lane[].busID
path[].subPath[].lane[].busLocalBlID
path[].subPath[].lane[].busCityCode
path[].subPath[].lane[].busProviderCode
path[].subPath[].intervalTime
path[].subPath[].startName
path[].subPath[].startX
path[].subPath[].startY
path[].subPath[].endName
path[].subPath[].endX
path[].subPath[].endY
path[].subPath[].startID
path[].subPath[].startStationCityCode
path[].subPath[].startStationProviderCode
path[].subPath[].startLocalStationID
path[].subPath[].startArsID
path[].subPath[].endID
path[].subPath[].endStationCityCode
path[].subPath[].endStationProviderCode
path[].subPath[].endLocalStationID
path[].subPath[].endArsID
path[].subPath[].passStopList
path[].subPath[].passStopList.stations
path[].subPath[].passStopList.stations[].index
path[].subPath[].passStopList.stations[].stationID
path[].subPath[].passStopList.stations[].stationName
path[].subPath[].passStopList.stations[].stationCityCode
path[].subPath[].passStopList.stations[].stationProviderCode
path[].subPath[].passStopList.stations[].localStationID
path[].subPath[].passStopList.stations[].arsID
path[].subPath[].passStopList.stations[].x
path[].subPath[].passStopList.stations[].y
path[].subPath[].passStopList.stations[].isNonStop
path[].subPath[].lane[].name
path[].subPath[].lane[].subwayCode
path[].subPath[].lane[].subwayCityCode
path[].subPath[].way
path[].subPath[].wayCode
path[].subPath[].door
path[].subPath[].startExitNo
path[].subPath[].startExitX
path[].subPath[].startExitY
path[].subPath[].endExitNo
path[].subPath[].endExitX
path[].subPath[].endExitY
```

## 2. 경로 요약 (총 15개)

| # | pathType | 총 시간(분) | 요금(원) | 구간 수 |
|---|---------|-----------|---------|--------|
| 0 | 2 | 40 | 2100 | 3 |
| 1 | 2 | 43 | 2100 | 3 |
| 2 | 2 | 45 | 2100 | 3 |
| 3 | 1 | 56 | 1800 | 5 |
| 4 | 2 | 65 | 1550 | 3 |
| 5 | 3 | 53 | 1600 | 5 |
| 6 | 3 | 59 | 1600 | 5 |
| 7 | 3 | 62 | 1600 | 5 |
| 8 | 3 | 58 | 2100 | 5 |
| 9 | 3 | 59 | 1800 | 5 |
| 10 | 3 | 52 | 2100 | 5 |
| 11 | 3 | 64 | 1600 | 5 |
| 12 | 3 | 55 | 2100 | 7 |
| 13 | 3 | 61 | 1600 | 5 |
| 14 | 3 | 66 | 1800 | 5 |

## 3. 필드 체크리스트

| 항목 | 결과 | 실제 필드명 | 샘플값 |
|------|------|-----------|--------|
| 총 소요시간 | ✅ 있음 | `path[].info.totalTime` | `40` |
| 총 요금 | ✅ 있음 | `path[].info.payment` | `2100` |
| 환승 횟수 | ✅ 있음 | `path[].info.busTransitCount` | `1` |
| 구간별 교통수단 종류 | ✅ 있음 | `path[].subPath[].trafficType` | `3` |
| 구간별 승차 정류장·역 | ✅ 있음 | `path[].subPath[].startName` | `부산역` |
| 구간별 하차 정류장·역 | ✅ 있음 | `path[].subPath[].endName` | `해운대해수욕장` |
| 구간별 소요시간 | ✅ 있음 | `path[].subPath[].sectionTime` | `1` |
| 배차간격 (구간별) | ✅ 있음 | `path[].subPath[].intervalTime` | `11` |
| 배차간격 (경로 합계) | ✅ 있음 | `path[].info.totalIntervalTime` | `11` |
| 도보 거리 | ✅ 있음 | `path[].info.totalWalk` | `189` |
| 도보 시간 | ✅ 있음 | `path[].info.totalWalkTime` | `-1` |

## 4. 첫 번째 경로의 구간 상세

| idx | 수단 | 노선 | 승차 | 하차 | 소요(분) | 배차간격(분) |
|-----|------|------|------|------|---------|------------|
| 0 | 도보 | - | - | - | 1 | 없음 |
| 1 | 버스 | 1003 | 부산역 | 해운대해수욕장 | 37 | 11 |
| 2 | 도보 | - | - | - | 2 | 없음 |
