HOST="${HOST:-http://localhost:8000}"

echo "Using host: ${HOST}"

curl -X POST ${HOST}/links/shorten \
    -H "Content-Type: application/json" \
    -d '{
          "url": "https://www.example.com",
          "expire_at": "2999-01-01T00:00:00",
          "alias": "myalias"
        }'

echo ""

locust -f locustfile.py --host=${HOST}
