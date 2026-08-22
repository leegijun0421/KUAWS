# 프론트엔드

아직 초기화되지 않았다. 프론트엔드 리드가 1주차에 아래를 실행한다.

```bash
cd frontend
npm create vite@latest . -- --template react-ts
npm install
npm install -D tailwindcss postcss autoprefixer
npx tailwindcss init -p
```

## 개발 원칙

- **백엔드를 기다리지 않는다.** `mocks/*.json` 을 import 해서 UI를 먼저 완성한다.
- API 호출은 `src/api/` 를 반드시 경유한다. 컴포넌트에서 직접 fetch 금지.
- 타입은 `shared/types/api.ts` 에서 import 한다. 프론트에서 타입을 새로 만들지 않는다.
- 3주차에 `src/api/` 의 목 반환을 실제 호출로 교체하면 전환이 끝난다.
