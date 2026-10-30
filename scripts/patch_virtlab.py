with open("/root/.openclaw/workspace/scripts/virtlab_cli.py", "r") as f:
    lines = f.readlines()

new_lines = []
for i, line in enumerate(lines):
    if "def instantiate_vm(" in line:
        new_lines.append("    def instantiate_vm(self, template_id, name, cpu=None, vcpu=None, memory_mb=None, network_id=None, ssh_public_key=None, hold=False, persistent=False):\n")
    elif "extra_template.append(f'NIC = [ NETWORK_ID = \"{network_id}\" ]')" in line:
        new_lines.append(line)
        new_lines.append("        if ssh_public_key is None and os.path.exists('/root/.ssh/id_ed25519.pub'):\n")
        new_lines.append("            try:\n")
        new_lines.append("                with open('/root/.ssh/id_ed25519.pub', 'r') as kf:\n")
        new_lines.append("                    ssh_public_key = kf.read().strip()\n")
        new_lines.append("            except Exception:\n")
        new_lines.append("                pass\n")
        new_lines.append("        if ssh_public_key:\n")
        new_lines.append("            extra_template.append(f'CONTEXT = [ NETWORK = \"YES\", SSH_PUBLIC_KEY = \"{ssh_public_key}\" ]')\n")
        new_lines.append("        elif network_id:\n")
        new_lines.append("            extra_template.append('CONTEXT = [ NETWORK = \"YES\" ]')\n")
    elif 'p_create.add_argument("--vnet-id"' in line:
        new_lines.append(line)
        new_lines.append("    p_create.add_argument('--ssh-key', type=str, default=None, help='SSH public key or path to public key file')\n")
    elif "res = client.instantiate_vm(" in line and i > 250:
        new_lines.append("            ssh_key = args.ssh_key\n")
        new_lines.append("            if ssh_key and os.path.exists(ssh_key):\n")
        new_lines.append("                try:\n")
        new_lines.append("                    with open(ssh_key, 'r') as kf:\n")
        new_lines.append("                        ssh_key = kf.read().strip()\n")
        new_lines.append("                except Exception:\n")
        new_lines.append("                    pass\n")
        new_lines.append(line)
    elif "network_id=args.vnet_id," in line and i > 250:
        new_lines.append(line)
        new_lines.append("                ssh_public_key=ssh_key,\n")
    else:
        new_lines.append(line)

with open("/root/.openclaw/workspace/scripts/virtlab_cli.py", "w") as f:
    f.writelines(new_lines)

print("SUCCESS")
