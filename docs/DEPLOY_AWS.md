# Deploy Aperture on AWS — one free-tier box (click by click)

This runs the **whole app** (database + API + worker + website) on a single small EC2
server using the containers the repo already ships. It stays inside the AWS **free tier**
if you follow the notes. Budget ~20–30 minutes end to end (most of it is the first build).

> **Read this first — safety & cost**
> - **Free tier is 12 months and limited.** Leaving the server running 24/7 for a full
>   month is within the free 750 hours for *one* t3.micro/t2.micro. A second instance,
>   or a bigger size, will cost money.
> - **Set a budget alarm (Step 0).** It's your safety net.
> - **This is a public sandbox.** It will be reachable on the internet with demo logins
>   (`123456`) and a demo endpoint. **Put no real personal or financial data in it.** For
>   a private demo, lock the firewall to your own IP in Step 1.
> - **It runs over plain HTTP** (no padlock). That's fine for a demo. Appendix A adds
>   HTTPS if you have a domain.
> - **Stop the server when you're not using it** (Step 5) and **delete it when done**
>   (Appendix B) so it never bills you.

---

## Step 0 — Set a billing budget alarm (2 min)

1. AWS console → search **Billing and Cost Management** → **Budgets** → **Create budget**.
2. Choose **Zero spend budget** (alerts the moment anything would cost money) — or a
   **Monthly cost budget** of **$5**. Enter your email. Create.

That's your seatbelt. Now the deploy.

---

## Step 1 — Launch the server (5 min)

1. Console → search **EC2** → **Launch instance**.
2. **Name:** `aperture-demo`.
3. **Application and OS Image:** pick **Ubuntu Server 24.04 LTS** (make sure it says
   *Free tier eligible*).
4. **Instance type:** pick **t3.micro** (or **t2.micro**) — whichever shows
   *Free tier eligible*.
5. **Key pair:** **Create new key pair** → name it `aperture-key` → **RSA / .pem** →
   Download it (you only need this if you want to SSH from your laptop; the browser
   "Connect" button in Step 2 doesn't need it).
6. **Network settings → Edit → Firewall (security group):** add these rules:
   - **SSH** · port **22** · Source **My IP**
   - **HTTP** · port **80** · Source **My IP** *(private demo — recommended)* or
     **Anywhere 0.0.0.0/0** *(anyone with the link can view it)*
7. **Configure storage:** set the disk to **30 GiB** (still free tier; the default 8 GiB
   is too small for the build).
8. **Launch instance.**

---

## Step 2 — Connect to the server (1 min)

1. EC2 → **Instances** → select `aperture-demo` → wait until **Status check** is green.
2. Click **Connect** → tab **EC2 Instance Connect** → **Connect**. A terminal opens in
   your browser (no SSH client or key needed).

*(Prefer your own terminal? `chmod 400 aperture-key.pem` then
`ssh -i aperture-key.pem ubuntu@<Public IPv4>`.)*

---

## Step 3 — Bring it up with one command (10–15 min)

Paste this into that browser terminal and press Enter:

```bash
curl -fsSL https://raw.githubusercontent.com/zssain/Aperture/demo-polish/deploy/aws/bootstrap.sh | bash
```

It installs Docker, adds swap (a t3.micro only has 1 GB RAM), fetches the code, builds
the containers, runs the database migrations, and seeds the demo. **The first build takes
about 10–15 minutes on this size** — that's normal. When it finishes it prints your URL
and the logins.

---

## Step 4 — Open it

Go to **`http://<your instance's Public IPv4>`** (copy the Public IPv4 from the EC2
instance page). You'll land on the public homepage → **Sign in** with any demo account:

| Role | Email | Password |
|---|---|---|
| Credit analyst | `creditanalyst@aperture.com` | `123456` |
| Policy owner | `policyowner@aperture.com` | `123456` |
| Fraud reviewer | `fraudreviewer@aperture.com` | `123456` |
| Auditor | `auditor@aperture.com` | `123456` |

---

## Step 5 — Operate it

From the server terminal (`cd ~/Aperture` first). The two `-f` flags are required every
time:

```bash
CMP="-f docker-compose.prod.yml -f docker-compose.aws.yml"
sudo docker compose $CMP ps           # what's running
sudo docker compose $CMP logs -f api  # tail API logs (Ctrl-C to stop)
sudo docker compose $CMP restart      # restart everything
sudo docker compose $CMP down         # stop the app (data is kept in a volume)
```

**Re-seed / reset the demo book** (e.g. after playing with it):
```bash
cd ~/Aperture && sudo -E PUBLIC_URL="http://$(curl -s -H "X-aws-ec2-metadata-token: $(curl -s -X PUT http://169.254.169.254/latest/api/token -H 'X-aws-ec2-metadata-token-ttl-seconds: 60')" http://169.254.169.254/latest/meta-data/public-ipv4)" \
  docker compose -f docker-compose.prod.yml -f docker-compose.aws.yml run --rm api python scripts/demo_reset.py
```

**Save free-tier hours when you're not demoing:** EC2 → Instances → select → **Instance
state → Stop**. **Start** it again before your next demo. (Its public IP changes on
stop/start unless you attach an Elastic IP; just re-copy the new IP.)

---

## Appendix A — Add HTTPS (optional, needs a domain)

Plain HTTP is fine for a demo. For a real padlock:
1. Point a domain's A-record at the instance's public IP (an Elastic IP so it's stable).
2. Put **Caddy** in front (it gets a free Let's Encrypt certificate automatically), or use
   an AWS Application Load Balancer with ACM (note: an ALB is **not** free — ~$16/mo).
3. Once on HTTPS, set `SESSION_COOKIE_SECURE=true` and `PUBLIC_URL=https://your-domain`
   in `docker-compose.aws.yml`, then `sudo docker compose $CMP up -d`.

## Appendix B — Tear down (stop all charges)

EC2 → Instances → select `aperture-demo` → **Instance state → Terminate**. Then EC2 →
**Volumes** → delete any leftover volume. That removes everything.

## Troubleshooting

| Symptom | Fix |
|---|---|
| Build killed / very slow | Swap is already added by the script. If it still struggles, use a **t3.small** for the build (not free) then switch back, or just retry — the build resumes from cache. |
| Site won't load | Check the security group has **port 80** open to your IP (Step 1.6), and you're using `http://` not `https://`. |
| Login says "incorrect" even with the right password | Only happens if it's served over HTTPS while `SESSION_COOKIE_SECURE=false`, or vice-versa. On plain HTTP keep it `false` (the default here). |
| Seed didn't run | `cd ~/Aperture` and re-run the re-seed command in Step 5. |
| Newly-eligible flip / demo endpoint 404s | Confirm `ENVIRONMENT=demo` (not `production`) in `docker-compose.aws.yml` — it's set that way by default. |
