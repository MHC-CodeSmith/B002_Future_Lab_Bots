# INSTALL.md — Instruções de Instalação e Operação (Fase 13)

## 1. Instalação dos Serviços Systemd de Usuário

No terminal do host (usuário `future-lab`):

```bash
# Copiar unidades para a pasta de serviços de usuário
mkdir -p ~/.config/systemd/user
cp ~/B002_Future_Lab_Bots/future_lab_control_center/host_agent/systemd/*.service ~/.config/systemd/user/
systemctl --user daemon-reload

# Habilitar e iniciar os serviços
systemctl --user enable --now future-lab-agent future-lab-cobot-discovery

# Habilitar Linger para que os serviços rodem sem sessão ativa
sudo loginctl enable-linger future-lab
```

## 2. Teste de Funcionamento do Agente

```bash
curl -s http://127.0.0.1:8100/health | jq .
```

## 3. Atalho na Área de Trabalho

```bash
cp ~/B002_Future_Lab_Bots/future_lab_control_center/FutureLab.desktop ~/Desktop/
cp ~/B002_Future_Lab_Bots/future_lab_control_center/FutureLab.desktop ~/.local/share/applications/
chmod +x ~/Desktop/FutureLab.desktop ~/.local/share/applications/FutureLab.desktop
```
*No ambiente GNOME, clique com botão direito no ícone da Área de Trabalho e selecione **Permitir Execução** (Allow Launching).*

## 4. Recuperação Manual da Create 3 (Se necessário)

- Interface web da base Create 3: `http://192.168.186.2` (via navegador ou proxy)
- Botão físico na sub-base para reset elétrico se houver travamento.
- **Aviso:** Nunca utilizar `ros2 service call /robot_power` para reinício automatizado pois desliga a sub-base.
