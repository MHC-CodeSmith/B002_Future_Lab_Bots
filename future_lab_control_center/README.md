# 🤖 Future Lab Control Center

Painel de Controle Web Unificado para Gestão e Operação da Célula Robótica do Laboratório (**MyCobot 280** + **TurtleBot 4**).

---

## 🌟 Recursos Principais

- **Monitoramento da Célula Integrada**: Player de controle mestre (`Iniciar`, `Pausar`, `Emergência/Home`) e seleção de modos (`Automático` vs `Manual`).
- **Controle & Visão do Cobot**: Transmissão em tempo real da câmera com overlay YOLO, ajuste de confiança (60%), cooldown pós-coleta (5s) e controle da bomba de sucção.
- **Modo Ensino (Teach Mode)**: Tabela com o status das 6 poses (`home`, `scan`, `pick_approach`, `pick`, `place_approach`, `place`), gravação com timestamp, playback e limpeza de calibragem.
- **Navegação do TurtleBot 4**: Monitoramento Nav2, gerenciamento de waypoints, nível de bateria e docking.
- **Diagnóstico Dinâmico de Rede**: Verificação de pings e conexões em tempo real (`HOST_PC`, `JETSON_NANO`, `TURTLEBOT`) com reconfiguração de IP via interface sem alterar código.

---

## 📁 Arquitetura do Projeto

```text
future_lab_control_center/
├── .env.example          # Modelo de configuração de rede (IPs e portas)
├── .env                  # Configuração local (ignorado pelo Git)
├── .gitignore            # Regras de exclusão do repositório
├── README.md             # Documentação do projeto
├── backend/              # Servidor Python (FastAPI + rclpy ROS 2)
│   ├── api/              # Endpoints REST e WebSockets
│   ├── config/           # Gerenciador dinâmico de rede
│   └── ros2_nodes/       # Nó ROS 2 de ponte com o hardware
└── frontend/             # Interface do Usuário (Next.js + TailwindCSS)
    ├── components/       # Widgets visuais da UI
    └── pages/            # Telas da aplicação
```
