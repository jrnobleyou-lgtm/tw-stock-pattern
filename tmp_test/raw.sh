for M in openai/gpt-4.1-mini; do
echo "== $M 簡短請求"
curl -sS -m 60 -i https://models.github.ai/inference/chat/completions -H "Authorization: Bearer $GITHUB_TOKEN" -H "Content-Type: application/json" -d "{\"model\":\"$M\",\"messages\":[{\"role\":\"user\",\"content\":\"請只回 JSON {\\\"ok\\\":1}\"}],\"response_format\":{\"type\":\"json_object\"}}" | head -30
echo "== 不帶 response_format"
curl -sS -m 60 -i https://models.github.ai/inference/chat/completions -H "Authorization: Bearer $GITHUB_TOKEN" -H "Content-Type: application/json" -d "{\"model\":\"$M\",\"messages\":[{\"role\":\"user\",\"content\":\"說 hi\"}]}" | head -30
echo "== 帶 api-version / accept"
curl -sS -m 60 -i https://models.github.ai/inference/chat/completions -H "Authorization: Bearer $GITHUB_TOKEN" -H "Accept: application/vnd.github+json" -H "X-GitHub-Api-Version: 2022-11-28" -H "Content-Type: application/json" -d "{\"model\":\"$M\",\"messages\":[{\"role\":\"user\",\"content\":\"說 hi\"}]}" | head -30
done
