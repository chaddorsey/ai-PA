# Remote Access Quick Reference

## Access Methods by Scenario

### 🟢 Normal Operation
| Method | Access | Purpose | Dependencies |
|--------|--------|---------|--------------|
| **RustDesk** | `rustdesk.cd-ai-pa.work:21116` | Desktop access, file transfer | Docker, desktop environment |
| **SSH** | `ssh user@server-ip` | Command line access | SSH enabled, network up |
| **Portainer** | `http://server-ip:9000` | Docker management | Docker running |
| **Cockpit** | `http://server-ip:9090` | System administration | System running |

### 🟡 Docker Services Down
| Method | Access | Purpose | Dependencies |
|--------|--------|---------|--------------|
| **SSH** | `ssh user@server-ip` | Restart Docker services | SSH enabled, network up |
| **Emergency Script** | `./scripts/system-recovery.sh` | Automated recovery | SSH access |

### 🔴 System Reboot Needed
| Method | Access | Purpose | Dependencies |
|--------|--------|---------|--------------|
| **SSH** | `ssh user@server-ip` | `sudo reboot` | SSH enabled, network up |
| **Emergency Script** | `./scripts/emergency-ssh.sh` | Restore SSH access | Physical access |

### ⚫ Complete System Failure
| Method | Access | Purpose | Dependencies |
|--------|--------|---------|--------------|
| **Physical Access** | Direct console | Hardware-level access | Physical presence |
| **Emergency Console** | Recovery mode | System recovery | Physical access |

## Quick Commands

### SSH Access
```bash
# Connect to server
ssh user@server-ip

# Connect with specific key
ssh -i ~/.ssh/id_ed25519 user@server-ip

# Connect to tmux session
ssh user@server-ip -t "tmux attach -t admin"
```

### Docker Management
```bash
# Check service status
docker-compose ps

# Restart all services
docker-compose restart

# Stop all services
docker-compose down

# Start all services
docker-compose up -d

# View logs
docker-compose logs -f service-name
```

### Emergency Recovery
```bash
# Restore SSH access
./scripts/emergency-ssh.sh

# System recovery
./scripts/system-recovery.sh

# RustDesk setup
./scripts/setup-rustdesk.sh
```

## Port Reference

| Port | Service | Purpose | Access |
|------|---------|---------|--------|
| 22 | SSH | Command line access | `ssh user@server-ip` |
| 80 | HTTP | Web services | `http://server-ip` |
| 443 | HTTPS | Secure web services | `https://server-ip` |
| 21115 | RustDesk ID | ID server (TCP) | RustDesk client |
| 21116 | RustDesk ID | ID server (UDP) | RustDesk client |
| 21117 | RustDesk Relay | Relay server | RustDesk client |
| 21118 | RustDesk Web | Web client | Browser |
| 21119 | RustDesk Web | Web client | Browser |
| 5678 | n8n | Workflow automation | `http://server-ip:5678` |
| 8080 | Open WebUI | AI interface | `http://server-ip:8080` |
| 8283 | Letta | Agent framework | `http://server-ip:8283` |
| 9000 | Portainer | Docker management | `http://server-ip:9000` |
| 9090 | Cockpit | System administration | `http://server-ip:9090` |

## External Access (via Cloudflare)

| Service | URL | Purpose |
|---------|-----|---------|
| RustDesk | `rustdesk.cd-ai-pa.work:21116` | Remote desktop |
| Portainer | `portainer.cd-ai-pa.work` | Docker management |
| Cockpit | `cockpit.cd-ai-pa.work` | System administration |
| n8n | `n8n.cd-ai-pa.work` | Workflow automation |
| Open WebUI | `webui.cd-ai-pa.work` | AI interface |

## Troubleshooting

### Can't Connect via SSH
1. Check if SSH is enabled: `sudo systemsetup -getremotelogin`
2. Enable SSH: `sudo systemsetup -setremotelogin on`
3. Check SSH service: `sudo launchctl list | grep ssh`
4. Start SSH: `sudo launchctl start com.openssh.sshd`

### Can't Connect via RustDesk
1. Check if Docker is running: `docker info`
2. Check RustDesk services: `docker-compose ps rustdesk-hbbs rustdesk-hbbr`
3. Restart RustDesk: `docker-compose restart rustdesk-hbbs rustdesk-hbbr`
4. Check public key: `docker exec rustdesk-hbbs cat /root/id_ed25519.pub`

### Can't Access Web Services
1. Check if services are running: `docker-compose ps`
2. Check port availability: `lsof -i :port-number`
3. Check firewall: `sudo ufw status`
4. Restart services: `docker-compose restart service-name`

### Docker Services Won't Start
1. Check Docker status: `docker info`
2. Check disk space: `df -h`
3. Check memory: `free -h`
4. Clean up Docker: `docker system prune -f`
5. Restart Docker: `open -a Docker`

## Security Notes

- Always use SSH keys instead of passwords
- Keep RustDesk public key secure
- Regularly update all services
- Monitor access logs
- Use strong passwords for web interfaces
- Enable 2FA where possible

## Backup Access Methods

If primary access methods fail:

1. **Physical Access**: Direct console access
2. **Emergency Console**: Recovery mode boot
3. **Network Boot**: PXE boot for recovery
4. **External Media**: Boot from USB/CD for recovery

## Emergency Contacts

- **System Administrator**: [Your contact info]
- **Network Administrator**: [Network admin contact]
- **Hardware Support**: [Hardware vendor contact]
- **Cloudflare Support**: [Cloudflare support contact]

## Maintenance Schedule

- **Daily**: Check service status
- **Weekly**: Test all access methods
- **Monthly**: Update services and security
- **Quarterly**: Test disaster recovery procedures
- **Annually**: Review and update access methods

