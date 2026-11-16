echo "== 模型清單"; curl -sS -m 60 -i https://models.github.ai/catalog/models -H "Authorization: Bearer $GITHUB_TOKEN" -H "Accept: application/vnd.github+json" | head -c 700
echo; echo "== 舊網址 azure gpt-4.1-mini"
curl -sS -m 60 -i https://models.inference.ai.azure.com/chat/completions -H "Authorization: Bearer $GITHUB_TOKEN" -H "Content-Type: application/json" -d '{"model":"gpt-4.1-mini","messages":[{"role":"user","content":"說 hi"}]}' | head -c 800
echo; echo "== 新網址 org 形式"
curl -sS -m 60 -i https://models.github.ai/orgs/jrnobleyou-lgtm/inference/chat/completions -H "Authorization: Bearer $GITHUB_TOKEN" -H "Accept: application/vnd.github+json" -H "Content-Type: application/json" -d '{"model":"openai/gpt-4.1-mini","messages":[{"role":"user","content":"說 hi"}]}' | head -c 800
echo; echo "== 新網址 GET"
curl -sS -m 60 -i https://models.github.ai/inference/chat/completions -H "Authorization: Bearer $GITHUB_TOKEN" | head -c 400
