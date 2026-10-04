# Mattermost Integration — Local Setup

## 1. Start Mattermost

```bash
just mattermost-up
```

This starts all regular services plus a local Mattermost on http://localhost:8065.

## 2. Configure Mattermost

1. Open http://localhost:8065 and create an admin account
2. Create a team (e.g. "Bouwmeester")
3. Create a bot account:
   - Go to **Integrations > Bot Accounts > Add Bot Account**
   - Username: `bouwmeester`
   - Role: System Admin (so it can DM anyone)
   - Copy the **access token**
4. Create a slash command:
   - Go to **Integrations > Slash Commands > Add Slash Command**
   - Command trigger: `bouwmeester`
   - Request URL: `http://backend:8000/api/mattermost/slash`
   - Request Method: POST
   - Copy the **token**
5. (Optional) Create a channel for broadcast notifications, copy its ID from the channel URL

## 3. Configure Bouwmeester

Add to `.env` in the project root:

```env
MATTERMOST_ENABLED=true
MATTERMOST_URL=http://mattermost:8065
MATTERMOST_BOT_TOKEN=<bot access token from step 3>
MATTERMOST_WEBHOOK_TOKEN=<slash command token from step 4>
MATTERMOST_NOTIFICATION_CHANNEL_ID=<channel ID from step 5>
```

Then add these to `docker-compose.yml` backend env (or they'll be picked up from `.env`):

```yaml
backend:
  environment:
    MATTERMOST_ENABLED: ${MATTERMOST_ENABLED:-false}
    MATTERMOST_URL: ${MATTERMOST_URL:-http://mattermost:8065}
    MATTERMOST_BOT_TOKEN: ${MATTERMOST_BOT_TOKEN:-}
    MATTERMOST_WEBHOOK_TOKEN: ${MATTERMOST_WEBHOOK_TOKEN:-}
    MATTERMOST_NOTIFICATION_CHANNEL_ID: ${MATTERMOST_NOTIFICATION_CHANNEL_ID:-}
```

Restart the backend:

```bash
just restart-backend
```

## 4. Link Your Account

1. Open Bouwmeester → Instellingen
2. In the "Mattermost koppeling" section, click **Genereer koppelcode**
3. Copy the code (e.g. `BM-a7f3x9`)
4. In Mattermost, DM the `@bouwmeester` bot with the code
5. The bot replies confirming the link

## 5. Test

- Assign a task to yourself in Bouwmeester → you should receive a DM in Mattermost
- Type `/bouwmeester taken` in Mattermost → see your open tasks
- Click "Taak afronden" on a notification → task is marked done

## Channel creation rights

The bot creates a channel per debate. Mattermost checks one permission for
that, `create_public_channel`, on the team the channel is created in. Header
and purpose travel with the create call, and pinning a post needs only channel
membership, so nothing else has to be granted.

`create_public_channel` is part of the default role of every team member
("All Members"), bots included. A server refuses only when an administrator
removed it, either system-wide or in a team that has its own permission
scheme. So check first:

```
GET /api/admin/mattermost-channel-rights
```

That asks Mattermost which permissions the bot holds and answers per team.
If `can_create_public_channel` is `false` for the team you need, a Mattermost
system administrator has two options:

- **System Console > User Management > Permissions**, open the scheme that
  applies to the team, and enable **Create Channels > Create public channels**
  under All Members. This gives the right to every team member.
- Make the bot a **Team Admin** in that team (team member list, then the role
  dropdown next to the bot). This leaves the scheme alone, and works as long
  as Team Admins still hold the permission.

A 503 from the endpoint means the question could not be answered (Mattermost
unreachable or disabled). That is not the same as "no".

## Architecture

```
Bouwmeester Frontend  →  Bouwmeester API  →  Mattermost API
                                ↑                   ↓
                          Worker (poller)    Bot DMs (link codes)
                                ↑                   ↓
                          Mattermost API  ←  Slash commands/actions
```

- **Notification mirror**: When a notification is created in Bouwmeester, it's also sent as a Mattermost DM (or channel post for broadcasts)
- **Account linking**: Users link via a short-lived code (generated in Bouwmeester, sent as DM to bot)
- **Slash commands**: `/bouwmeester taken|zoek|status|help` — processed by the backend
- **Interactive buttons**: "Bekijken" (deep link) and "Taak afronden" (completes via API)
