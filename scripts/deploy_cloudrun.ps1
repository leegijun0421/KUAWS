<#
.SYNOPSIS
  모두의 여행(KUAWS)을 Google Cloud Run 에 배포한다. 컨테이너 1개 = 화면 + API.

.DESCRIPTION
  실행 위치: Windows PowerShell, C:\project\KUAWS (리포 루트)
  사전 준비: Google Cloud SDK 설치 + `gcloud auth login` 1회 (docs/DEPLOY.md 참고)

  - 키는 리포 루트 .env 에서 읽어 Cloud Run 환경변수로만 넣는다(이미지·Git 에 들어가지 않음).
  - Cloud Run 은 나가는 IP 가 고정되지 않는다. IP 제한이 걸린 키 A 는 여기서 실패하므로
    .env 에 GOOGLE_CLOUDRUN_API_KEY(Routes·Places API 제한만 건 배포용 키)를 넣어 두면 그 키를 쓴다.

.EXAMPLE
  .\scripts\deploy_cloudrun.ps1 -ProjectId my-gcp-project
#>
param(
    [Parameter(Mandatory = $true)][string]$ProjectId,
    [string]$Region = "asia-northeast3",   # 서울
    [string]$Service = "kuaws"
)

$ErrorActionPreference = "Stop"
Set-Location (Split-Path $PSScriptRoot -Parent)

# ── 1. .env 읽기 (BOM 허용) ────────────────────────────────────────────────
if (-not (Test-Path ".env")) { throw ".env 가 없습니다. 리포 루트에서 실행하세요." }
$envMap = @{}
Get-Content ".env" -Encoding UTF8 | ForEach-Object {
    $line = $_.Trim().TrimStart([char]0xFEFF)
    if ($line -and -not $line.StartsWith("#") -and $line.Contains("=")) {
        $k, $v = $line.Split("=", 2)
        $envMap[$k.Trim()] = $v.Trim()
    }
}
$anthropic = $envMap["ANTHROPIC_API_KEY"]
$backendKey = $envMap["GOOGLE_CLOUDRUN_API_KEY"]
if (-not $backendKey) {
    $backendKey = $envMap["GOOGLE_BACKEND_API_KEY"]
    Write-Warning "GOOGLE_CLOUDRUN_API_KEY 가 없어 키 A(GOOGLE_BACKEND_API_KEY)를 씁니다. 키 A 에 IP 제한이 있으면 경로 조회가 403 으로 실패합니다."
}
if (-not $anthropic -or -not $backendKey) { throw ".env 에 ANTHROPIC_API_KEY / Google 백엔드 키가 비어 있습니다." }
if (-not (Test-Path "frontend\.env.local")) { Write-Warning "frontend\.env.local(지도 키 B)이 없어 지도 없이 배포됩니다." }
if (-not (Test-Path "data\processed\pois\paris\tagged.json")) { Write-Warning "수집된 POI 가 없어 예시 장소(mocks/poi_seed)로 배포됩니다." }

# ── 2. 프로젝트·API 활성화 ────────────────────────────────────────────────
gcloud config set project $ProjectId
gcloud services enable run.googleapis.com cloudbuild.googleapis.com artifactregistry.googleapis.com

# ── 3. 소스 업로드 → Cloud Build 가 Dockerfile 로 빌드 → Cloud Run 배포 ────────
#   min-instances 1 : 심사 중 첫 접속 지연(콜드 스타트)·공유 링크 DB 초기화를 줄인다
#   max-instances 2 : 트래픽 폭주 시 API 요금 상한 역할
$envVars = "ANTHROPIC_API_KEY=$anthropic,GOOGLE_BACKEND_API_KEY=$backendKey"
gcloud run deploy $Service `
    --source . `
    --region $Region `
    --allow-unauthenticated `
    --memory 1Gi --cpu 1 `
    --min-instances 1 --max-instances 2 `
    --timeout 120 `
    --set-env-vars $envVars
if ($LASTEXITCODE -ne 0) { throw "배포 실패 — 위 로그를 확인하세요." }

# ── 4. 공유 링크가 배포 주소를 가리키도록 PUBLIC_BASE_URL 설정 ────────────────
$url = (gcloud run services describe $Service --region $Region --format "value(status.url)").Trim()
gcloud run services update $Service --region $Region --update-env-vars "PUBLIC_BASE_URL=$url"

Write-Host ""
Write-Host "배포 완료: $url" -ForegroundColor Green
Write-Host "확인: $url/health  →  {`"status`":`"ok`"}"
Write-Host "남은 일: GCP 콘솔 > API 및 서비스 > 사용자 인증 정보 > 키 B 의 HTTP 리퍼러에 '$url/*' 추가 (지도 표시용)"
