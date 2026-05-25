# Webhook signature verification — working examples

This document shows production-ready code for verifying EnterpriseCore's
outbound webhook HMAC-SHA256 signature in six languages. Every example is
copy-paste ready; substitute the secret returned by
`POST /api/v1/webhooks/subscriptions` and you're done.

For the high-level event catalog, see [WEBHOOKS.md](WEBHOOKS.md). For
EnterpriseCore's broader security posture, see
[SECURITY_HARDENING.md](SECURITY_HARDENING.md).

## Headers EnterpriseCore sends

Every outbound POST carries the following request headers:

| Header             | Example                                             | Meaning                                               |
| ------------------ | --------------------------------------------------- | ----------------------------------------------------- |
| `X-EC-Signature`   | `sha256=4d54a3...`                                  | Hex HMAC-SHA256 of the raw body using your secret.    |
| `X-EC-Timestamp`   | `2026-05-23T09:14:21.117482+00:00`                  | ISO-8601 UTC timestamp of when the event was sent.    |
| `X-EC-Event-Id`    | `01HXK7AYJ0M9V2N1ZS6Q3D4F5G`                        | ULID — use as your idempotency key.                   |
| `X-EC-Event-Type`  | `crm.deal.won`                                      | Canonical event type from the EnterpriseCore catalog. |
| `X-EC-Attempt`     | `1`                                                 | Retry attempt counter (1 on first try).               |
| `Content-Type`     | `application/json`                                  | Always.                                               |
| `User-Agent`       | `EnterpriseCore-Webhooks/1.0`                       | Static identifier.                                    |

The body is canonical JSON — verify against the **raw bytes**, not a
re-serialised representation. Most frameworks let you read the raw body
either before or alongside the parsed form; the examples below show how.

## Body shape

```json
{
  "id": "01HXK7AYJ0M9V2N1ZS6Q3D4F5G",
  "type": "crm.deal.won",
  "tenant_id": "01HV...",
  "user_id": "01HV...",
  "occurred_at": "2026-05-23T09:14:21.117482+00:00",
  "payload": {
    "deal_id": "01HW...",
    "amount_cents": 4500000,
    "currency": "USD",
    "customer_name": "Acme Co."
  }
}
```

## Security note — replay protection

Always verify that `X-EC-Timestamp` is within ±5 minutes of your server's
clock. An attacker who exfiltrates one webhook delivery (e.g. from a
captured log) could otherwise replay it forever. Every example below
includes the replay guard.

## Sample raw HTTP request

```http
POST /webhooks/enterprisecore HTTP/1.1
Host: hooks.example.com
Content-Type: application/json
User-Agent: EnterpriseCore-Webhooks/1.0
X-EC-Signature: sha256=4d54a3f0e7c2c7f3b18a85f7d1f4e0b3a2a8d4c9f6e2b1d0a9c8b7e6f5d4c3b2
X-EC-Timestamp: 2026-05-23T09:14:21.117482+00:00
X-EC-Event-Id: 01HXK7AYJ0M9V2N1ZS6Q3D4F5G
X-EC-Event-Type: crm.deal.won
X-EC-Attempt: 1
Content-Length: 257

{"id":"01HXK7AYJ0M9V2N1ZS6Q3D4F5G","type":"crm.deal.won","tenant_id":"01HV...","user_id":"01HV...","occurred_at":"2026-05-23T09:14:21.117482+00:00","payload":{"deal_id":"01HW...","amount_cents":4500000,"currency":"USD","customer_name":"Acme Co."}}
```

## Python (Flask + raw `hmac`)

```python
# requirements: flask
import hmac
import hashlib
from datetime import datetime, timezone, timedelta
from flask import Flask, request, abort

app = Flask(__name__)
WEBHOOK_SECRET = b"<paste-the-secret-from-subscription-create>"
MAX_DRIFT = timedelta(minutes=5)


def verify_signature(body: bytes, header_sig: str, secret: bytes) -> bool:
    if not header_sig or not header_sig.startswith("sha256="):
        return False
    expected = hmac.new(secret, body, hashlib.sha256).hexdigest()
    received = header_sig.split("=", 1)[1]
    return hmac.compare_digest(expected, received)


def verify_timestamp(ts_header: str) -> bool:
    if not ts_header:
        return False
    try:
        sent = datetime.fromisoformat(ts_header)
    except ValueError:
        return False
    return abs(datetime.now(timezone.utc) - sent) <= MAX_DRIFT


@app.post("/webhooks/enterprisecore")
def receive_webhook():
    raw_body = request.get_data()  # MUST be raw bytes
    sig = request.headers.get("X-EC-Signature", "")
    ts = request.headers.get("X-EC-Timestamp", "")

    if not verify_timestamp(ts):
        abort(400, "stale or missing timestamp")
    if not verify_signature(raw_body, sig, WEBHOOK_SECRET):
        abort(401, "bad signature")

    event = request.get_json()
    # Use X-EC-Event-Id as the idempotency key in your downstream store.
    handle_event(event)
    return "", 204


def handle_event(event):  # placeholder
    print(event["type"], event["payload"])
```

Equivalent FastAPI handler:

```python
from fastapi import FastAPI, Header, HTTPException, Request

app = FastAPI()

@app.post("/webhooks/enterprisecore")
async def receive(
    request: Request,
    x_ec_signature: str = Header(""),
    x_ec_timestamp: str = Header(""),
):
    raw = await request.body()
    if not verify_timestamp(x_ec_timestamp):
        raise HTTPException(400, "stale or missing timestamp")
    if not verify_signature(raw, x_ec_signature, WEBHOOK_SECRET):
        raise HTTPException(401, "bad signature")
    return {"ok": True}
```

## Node.js (Express + `crypto`)

```js
// npm i express body-parser
const express = require("express");
const bodyParser = require("body-parser");
const crypto = require("crypto");

const WEBHOOK_SECRET = "<paste-the-secret>";
const MAX_DRIFT_MS = 5 * 60 * 1000;

function verifySignature(rawBody, headerSig, secret) {
  if (!headerSig || !headerSig.startsWith("sha256=")) return false;
  const expected = crypto
    .createHmac("sha256", secret)
    .update(rawBody)
    .digest("hex");
  const received = headerSig.slice("sha256=".length);
  // Constant-time comparison.
  const a = Buffer.from(expected, "hex");
  const b = Buffer.from(received, "hex");
  return a.length === b.length && crypto.timingSafeEqual(a, b);
}

function verifyTimestamp(ts) {
  if (!ts) return false;
  const sent = Date.parse(ts);
  if (Number.isNaN(sent)) return false;
  return Math.abs(Date.now() - sent) <= MAX_DRIFT_MS;
}

const app = express();
// IMPORTANT: capture the raw body for signature verification.
app.use(
  bodyParser.json({
    verify: (req, _res, buf) => {
      req.rawBody = buf;
    },
  })
);

app.post("/webhooks/enterprisecore", (req, res) => {
  const sig = req.get("X-EC-Signature") || "";
  const ts = req.get("X-EC-Timestamp") || "";

  if (!verifyTimestamp(ts)) {
    return res.status(400).send("stale or missing timestamp");
  }
  if (!verifySignature(req.rawBody, sig, WEBHOOK_SECRET)) {
    return res.status(401).send("bad signature");
  }
  // req.body is parsed JSON; req.get("X-EC-Event-Id") is the idempotency key.
  handleEvent(req.body);
  res.status(204).end();
});
```

## PHP (vanilla + `hash_hmac`)

```php
<?php
// hooks.php — drop into any PHP-enabled webroot.
$WEBHOOK_SECRET = '<paste-the-secret>';
$MAX_DRIFT     = 5 * 60; // seconds

$rawBody  = file_get_contents('php://input');
$headers  = getallheaders();
$sig      = $headers['X-EC-Signature']  ?? '';
$ts       = $headers['X-EC-Timestamp']  ?? '';

function verify_signature(string $body, string $headerSig, string $secret): bool {
    if (substr($headerSig, 0, 7) !== 'sha256=') return false;
    $expected = hash_hmac('sha256', $body, $secret);
    $received = substr($headerSig, 7);
    return hash_equals($expected, $received);
}

function verify_timestamp(string $ts, int $maxDrift): bool {
    if ($ts === '') return false;
    $sent = strtotime($ts);
    if ($sent === false) return false;
    return abs(time() - $sent) <= $maxDrift;
}

if (!verify_timestamp($ts, $MAX_DRIFT)) {
    http_response_code(400); echo 'stale or missing timestamp'; exit;
}
if (!verify_signature($rawBody, $sig, $WEBHOOK_SECRET)) {
    http_response_code(401); echo 'bad signature'; exit;
}

$event = json_decode($rawBody, true);
// $headers['X-EC-Event-Id'] is your idempotency key.
handle_event($event);
http_response_code(204);
```

## Ruby (Rack / Sinatra + `OpenSSL::HMAC`)

```ruby
# Gemfile: gem "sinatra"
require "sinatra"
require "openssl"
require "json"
require "time"

WEBHOOK_SECRET = "<paste-the-secret>"
MAX_DRIFT = 5 * 60  # seconds

def verify_signature(body, header_sig, secret)
  return false unless header_sig&.start_with?("sha256=")
  expected = OpenSSL::HMAC.hexdigest("SHA256", secret, body)
  received = header_sig.split("=", 2).last
  # Rack::Utils.secure_compare is constant-time.
  Rack::Utils.secure_compare(expected, received)
end

def verify_timestamp(ts)
  return false if ts.nil? || ts.empty?
  sent = Time.iso8601(ts) rescue nil
  return false unless sent
  (Time.now.utc - sent).abs <= MAX_DRIFT
end

post "/webhooks/enterprisecore" do
  request.body.rewind
  raw = request.body.read
  sig = request.env["HTTP_X_EC_SIGNATURE"]
  ts  = request.env["HTTP_X_EC_TIMESTAMP"]

  halt 400, "stale or missing timestamp" unless verify_timestamp(ts)
  halt 401, "bad signature" unless verify_signature(raw, sig, WEBHOOK_SECRET)

  event = JSON.parse(raw)
  handle_event(event)
  status 204
end
```

## Go (net/http + `crypto/hmac`)

```go
// main.go
package main

import (
    "crypto/hmac"
    "crypto/sha256"
    "encoding/hex"
    "io"
    "net/http"
    "strings"
    "time"
)

var webhookSecret = []byte("<paste-the-secret>")

const maxDrift = 5 * time.Minute

func verifySignature(body []byte, headerSig string, secret []byte) bool {
    if !strings.HasPrefix(headerSig, "sha256=") {
        return false
    }
    mac := hmac.New(sha256.New, secret)
    mac.Write(body)
    expected := mac.Sum(nil)
    received, err := hex.DecodeString(strings.TrimPrefix(headerSig, "sha256="))
    if err != nil {
        return false
    }
    return hmac.Equal(expected, received)
}

func verifyTimestamp(ts string) bool {
    if ts == "" {
        return false
    }
    sent, err := time.Parse(time.RFC3339Nano, ts)
    if err != nil {
        return false
    }
    drift := time.Since(sent)
    if drift < 0 {
        drift = -drift
    }
    return drift <= maxDrift
}

func handleWebhook(w http.ResponseWriter, r *http.Request) {
    body, err := io.ReadAll(r.Body)
    if err != nil {
        http.Error(w, "cannot read body", http.StatusBadRequest)
        return
    }
    sig := r.Header.Get("X-EC-Signature")
    ts := r.Header.Get("X-EC-Timestamp")
    if !verifyTimestamp(ts) {
        http.Error(w, "stale or missing timestamp", http.StatusBadRequest)
        return
    }
    if !verifySignature(body, sig, webhookSecret) {
        http.Error(w, "bad signature", http.StatusUnauthorized)
        return
    }
    // r.Header.Get("X-EC-Event-Id") is your idempotency key.
    w.WriteHeader(http.StatusNoContent)
}

func main() {
    http.HandleFunc("/webhooks/enterprisecore", handleWebhook)
    http.ListenAndServe(":8080", nil)
}
```

## Java (Spring Boot + `javax.crypto.Mac`)

```java
// build.gradle: implementation "org.springframework.boot:spring-boot-starter-web"
package com.example.hooks;

import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.*;

import javax.crypto.Mac;
import javax.crypto.spec.SecretKeySpec;
import java.nio.charset.StandardCharsets;
import java.time.*;
import java.time.format.DateTimeParseException;
import java.util.HexFormat;

@RestController
public class WebhookController {
    private static final byte[] SECRET =
        "<paste-the-secret>".getBytes(StandardCharsets.UTF_8);
    private static final Duration MAX_DRIFT = Duration.ofMinutes(5);

    private boolean verifySignature(byte[] body, String headerSig) throws Exception {
        if (headerSig == null || !headerSig.startsWith("sha256=")) return false;
        Mac mac = Mac.getInstance("HmacSHA256");
        mac.init(new SecretKeySpec(SECRET, "HmacSHA256"));
        byte[] expected = mac.doFinal(body);
        byte[] received = HexFormat.of().parseHex(headerSig.substring(7));
        return constantTimeEquals(expected, received);
    }

    private boolean constantTimeEquals(byte[] a, byte[] b) {
        if (a.length != b.length) return false;
        int diff = 0;
        for (int i = 0; i < a.length; i++) diff |= a[i] ^ b[i];
        return diff == 0;
    }

    private boolean verifyTimestamp(String ts) {
        if (ts == null || ts.isEmpty()) return false;
        try {
            Instant sent = OffsetDateTime.parse(ts).toInstant();
            return Duration.between(sent, Instant.now()).abs().compareTo(MAX_DRIFT) <= 0;
        } catch (DateTimeParseException e) {
            return false;
        }
    }

    @PostMapping(value = "/webhooks/enterprisecore", consumes = "application/json")
    public ResponseEntity<Void> receive(
            @RequestBody byte[] rawBody,
            @RequestHeader("X-EC-Signature") String sig,
            @RequestHeader("X-EC-Timestamp") String ts) throws Exception {
        if (!verifyTimestamp(ts))
            return ResponseEntity.badRequest().build();
        if (!verifySignature(rawBody, sig))
            return ResponseEntity.status(401).build();
        // Use the X-EC-Event-Id header as your idempotency key.
        return ResponseEntity.noContent().build();
    }
}
```

## Failure modes worth handling

1. **Timestamp drift.** Receiver clocks that drift more than 5 minutes will
   reject every webhook. Run NTP. Adjust `MAX_DRIFT` only as a last resort
   and never above 15 minutes.
2. **Replays from a captured delivery.** Without the timestamp check, an
   attacker with one signed payload can replay it forever. The timestamp
   guard is non-optional.
3. **Mutated body.** Middleware that re-encodes JSON (Express's default
   `body-parser`, certain logging proxies) will silently invalidate every
   signature. Always verify against the raw bytes you received on the
   wire.
4. **Idempotency.** EnterpriseCore retries failed deliveries with
   exponential backoff. Store `X-EC-Event-Id` for at least 24 hours and
   short-circuit duplicate processing.
5. **Secret rotation.** Rotate the subscription secret on a schedule via
   `POST /api/v1/webhooks/subscriptions/{id}/rotate-secret`. Keep the old
   secret accepted for a grace period during rollover.
