# B002 Future Lab Bots

Repositorio agregador para manter juntos os tres projetos do laboratorio B002:
TurtleBot4, MyCobot e a camada de integracao/visualizacao 3D. Cada pasta e um
submodulo Git; este repositorio salva quais versoes dos tres devem andar juntas.

## Estrutura

```text
B002_Future_Lab_Bots/
  turtlebot4_jazzy/       # TurtleBot4 Jazzy, mapa B002, Nav2 e rotinas
  cobot/                  # MyCobot, Docker, MoveIt e bridge do braco
  integration_cobot_tb4/  # visualizacao 3D, overlay e ponte de juntas
```

Os diretorios antigos em `/home/mhc/Germany/turtlebot4_jazzy`,
`/home/mhc/Germany/Cobot` e `/home/mhc/Germany/cobot_tb4_integration` ainda
funcionam, mas o caminho preferido para novos testes e:

```bash
cd /home/mhc/Germany/B002_Future_Lab_Bots
```

## Referencias oficiais usadas

Para manter cada robo proximo do uso recomendado, a base foi feita a partir dos
tutoriais oficiais de cada plataforma.

### TurtleBot4

- [TurtleBot4 basic setup](https://turtlebot.github.io/turtlebot4-user-manual/setup/basic.html)
- [TurtleBot4 navigation tutorial](https://turtlebot.github.io/turtlebot4-user-manual/tutorials/navigation.html)
- Issues e limitacoes observadas: [turtlebot4_jazzy/KNOWN_ISSUES.md](turtlebot4_jazzy/KNOWN_ISSUES.md)

### MyCobot

- [Elephant Robotics GitBook](https://docs.elephantrobotics.com/docs/gitbook-en/)
- [MyCobot 280 Pi SSH/software notes](https://docs.elephantrobotics.com/docs/mycobot_280_pi_en/3-FunctionsAndApplications/5.BasicFunction/5.2-Softwarelnstructions/3.5.2-SW-detail-description.html#ssh)
- [MyCobot 280 MoveIt documentation](https://docs.elephantrobotics.com/docs/mycobot-m5-en/12-ApplicationBaseROS/12.1-ROS1/12.1.5-Moveit/myCobot-280.html)
- [MyCobot 280 Arduino ROS/MoveIt documentation](https://docs.elephantrobotics.com/docs/mycobot-280-Arduino-en/3-FunctionsAndApplications/6.developmentGuide/ROS/12.1-ROS1/12.1.5-Moveit/)
- [MoveIt 2 Galactic README](https://github.com/moveit/moveit2/tree/galactic?tab=readme-ov-file)
- [MoveIt Galactic announcement](https://moveit.ai/ros/moveit/galactic/2021/07/08/moveit-galactic.html)
- [Install MoveIt 2 from source](https://moveit.ai/install-moveit2/source/)
- [Elephant Robotics MyCobot 280 Jetson Nano support](https://www.elephantrobotics.com/en/support-280-jetson-nano-en/)

### Network and factory references

- Router/lab network: TP-Link AX5400.
- Factory PDFs used locally during integration:
  - `/home/mhc/Downloads/System Overview Hof University 1.pdf`
  - `/home/mhc/Downloads/0Q7_00001-ENG_Teil_1.pdf`
  - `/home/mhc/Downloads/109737901_OPC_UA_Client_S7-1500_DOKU_V1_5_en.pdf`

## Clonar tudo

```bash
git clone --recurse-submodules https://github.com/MHC-CodeSmith/B002_Future_Lab_Bots.git
cd B002_Future_Lab_Bots
```

Se ja clonou sem submodulos:

```bash
git submodule update --init --recursive
```

Para atualizar as versoes dos tres submodulos:

```bash
git pull
git submodule update --init --recursive
```

## Como rodar os tres sistemas

A forma pratica de operar no laboratorio e abrir tres janelas no Terminator e
deixar cada janela em uma parte do sistema: MyCobot, TurtleBot4 e integracao 3D.

Antes de comecar, pare processos antigos de RViz/Nav2/mission manager se a
sessao anterior falhou:

```bash
pkill -f "mission_manager.py" || true
pkill -f "turtlebot4_navigation localization.launch.py" || true
pkill -f "turtlebot4_navigation nav2.launch.py" || true
pkill -f "turtlebot4_viz view_navigation.launch.py" || true
pkill -f "rviz2" || true
ros2 daemon stop
ros2 daemon start
```

### Janela 1 - MyCobot

```bash
cd /home/mhc/Germany/B002_Future_Lab_Bots/cobot/mycobot_docker
xhost +local:root
docker compose up -d mycobot_ros2
```

Depois rode o planejamento/MoveIt no PC:

```bash
cd /home/mhc/Germany/B002_Future_Lab_Bots/cobot
./mycobot_docker/RUN_PLANNING_PC.sh
```

Esse fluxo sobe o container, prepara o bridge do MyCobot e abre MoveIt/RViz para
planejar e executar movimentos do braco.

### Janela 2 - TurtleBot4 fisico no mapa B002

Entre no workspace do TurtleBot4:

```bash
cd /home/mhc/Germany/B002_Future_Lab_Bots/turtlebot4_jazzy
source /opt/ros/jazzy/setup.bash
export ROS_DOMAIN_ID=0
export ROS_AUTOMATIC_DISCOVERY_RANGE=SUBNET
export RMW_IMPLEMENTATION=rmw_fastrtps_cpp
export ROS_SUPER_CLIENT=True
export ROS_DISCOVERY_SERVER="192.168.0.129:11811;"
```

Se o robo estiver dockado, primeiro faca undock:

```bash
ros2 action send_goal /undock irobot_create_msgs/action/Undock "{}"
```

Depois suba a localizacao com o mapa B002:

```bash
ros2 launch turtlebot4_navigation localization.launch.py \
  map:=/home/mhc/Germany/B002_Future_Lab_Bots/turtlebot4_jazzy/maps/B002_map.yaml
```

Quando o mapa aparecer no RViz, use **2D Pose Estimate** para setar a pose
inicial do robo no mapa. Depois suba o Nav2 com os parametros do projeto:

```bash
ros2 launch turtlebot4_navigation nav2.launch.py \
  params_file:=/home/mhc/Germany/B002_Future_Lab_Bots/turtlebot4_jazzy/config/nav2_custom.yaml
```

Quando os controllers estiverem ativos, abra a visualizacao de navegacao:

```bash
ros2 launch turtlebot4_viz view_navigation.launch.py
```

### Janela 3 - Visualizacao 3D integrada

```bash
cd /home/mhc/Germany/B002_Future_Lab_Bots/integration_cobot_tb4
source /opt/ros/jazzy/setup.bash
export ROS_DOMAIN_ID=0
export ROS_AUTOMATIC_DISCOVERY_RANGE=SUBNET
export RMW_IMPLEMENTATION=rmw_fastrtps_cpp
export ROS_SUPER_CLIENT=True
export ROS_DISCOVERY_SERVER="192.168.0.129:11811;"
./scripts/run_3d_view.sh
```

### Configuração de Chave SSH sem Senha (PC ↔ Robô)

Para que o script `mission_manager.py` consiga ligar a câmera OAK-D no robô automaticamente via SSH, você precisa autorizar a chave SSH do seu PC no robô:

1. Gere uma chave SSH no PC (se já não tiver uma):
   ```bash
   ssh-keygen -t ed25519 -N "" -f ~/.ssh/id_ed25519
   ```
2. Copie a chave para o robô:
   ```bash
   ssh-copy-id ubuntu@192.168.0.129
   ```
   *(Insira a senha do usuário `ubuntu` do robô quando solicitado).*

### Janela 2 ou nova aba - Mission manager

Depois que localizacao, Nav2 e sensores estiverem estaveis:

```bash
cd /home/mhc/Germany/B002_Future_Lab_Bots/turtlebot4_jazzy
source /opt/ros/jazzy/setup.bash
export ROS_DOMAIN_ID=0
export ROS_AUTOMATIC_DISCOVERY_RANGE=SUBNET
export RMW_IMPLEMENTATION=rmw_fastrtps_cpp
export ROS_SUPER_CLIENT=True
export ROS_DISCOVERY_SERVER="192.168.0.129:11811;"
python3 scripts/mission_manager.py --ros-args --params-file params/waypoints.yaml
```

Para iniciar a rotina de delivery:

```bash
ros2 service call /start_delivery std_srvs/srv/Trigger {}
```

## Simulacao

Para testar o TurtleBot4 em Gazebo com o ambiente Docker do projeto:

```bash
cd /home/mhc/Germany/B002_Future_Lab_Bots/turtlebot4_jazzy
./sim/run_lab_world.sh false false 0.0 0.0 0.0
```

A simulacao e util para desenvolvimento, mas nao substitui totalmente os testes
fisicos no B002: dock/undock, RPLidar, OAK-D, Wi-Fi e a recuperacao dos sensores
apos undock podem se comportar diferente no robo real.

## Observacoes de integracao

- TurtleBot4: ROS 2 Jazzy, FastDDS, `ROS_DOMAIN_ID=0`.
- MyCobot: ROS 2 Galactic, MoveIt 2, bridge DDS separado para o braco.
- Integracao 3D: nao controla o robo nem o braco; ela visualiza os dois no
  mesmo frame `map`.
- O mapa usado para navegacao e `turtlebot4_jazzy/maps/B002_map.yaml`.
- Os waypoints usados pelas rotinas ficam em `turtlebot4_jazzy/params/waypoints.yaml`.

---

## 🎛️ Future Lab Control Center (Dashboard Web & Célula Robótica)

A pasta `future_lab_control_center/` contém a interface web completa de supervisão, controle e calibração da célula robótica.

### Arquitetura de Comunicação e Portas

```text
  [ Frontend Next.js (Porta 3000) ]
                 │ (HTTP REST / Polling)
                 ▼
  [ Backend FastAPI (Porta 8000) ] ── (ROS 2 DDS / Docker) ──► [ MoveIt Planning (mycobot_ros2) ]
                 │ (SSH ControlMaster / HTTP Micro-Bridge)
                 ▼
  [ Jetson Nano (192.168.0.250) ]
     ├── HTTP Micro-Bridge (Porta 8088) -> Bomba, Soltar/Travar Motores, Direct Joints (<30ms)
     └── Servidor Câmera MJPEG (Porta 8080) -> Stream ao vivo de visão computacional
```

---

### 🚨 Documentação do Modo Pânico (Panic Mode) e Limitações de Hardware

O botão **`🚨 BOTÃO DE PÂNICO`** no Dashboard executa uma parada master de segurança da célula robótica.

#### Sequência de Execução do Pânico:
1. **Trava Físico-Mecânica (`< 5ms`)**: Envia uma requisição HTTP prioritária para `http://192.168.0.250:8088/panic`, interrompendo o envio de novas posições seriais e forçando o travamento de torque em todas as 6 juntas no microcontrolador da base MyCobot.
2. **Desligamento de Periféricos**: Desliga a bomba de sucção e mata o teste de visão YOLO.
3. **Parada da Câmera**: Encerra o processo `nano_camera_server.py` na Jetson Nano.
4. **Encerramento do Planejador MoveIt**: Executa `pkill -9` nos nós `move_group` e `rviz` dentro do container Docker `mycobot_ros2` no PC.
5. **Encerramento da Ponte Nano**: Mata o nó `mycobot_bridge` na Jetson Nano (as juntas permanecem energizadas/travadas pela placa de controle do robô).
6. **Panic Lockout**: Bloqueia o Dashboard em estado de segurança até que o usuário solicite a reinicialização.

#### ⚠️ Más Otimizações Conhecidas, Gargalos e Cuidados Futuros:

> [!WARNING]
> **1. Contenção da Porta Serial (`/dev/ttyTHS1`) na Jetson Nano**:
> Ao encerrar abruptamente o nó `mycobot_bridge` na Jetson Nano com `pkill -9`, o driver serial do kernel Linux pode demorar até **1 a 2 segundos** para liberar totalmente a porta `/dev/ttyTHS1`. Se a reinicialização for disparada antes dessa liberação, a comunicação serial pode falhar com o erro `device reports readiness to read but returned no data` ou a porta `8088` indicar `Address already in use`.

> [!WARNING]
> **2. Inércia de Buffer do Firmware Interno (MyCobot 280)**:
> Se o Pânico for acionado enquanto o braço está em movimento de velocidade alta (ex: retorno para `HOME`), a ordem de pânico HTTP é enviada em `< 5ms`, mas o robô físico ainda pode deslocar de 1cm a 3cm devido aos pacotes já armazenados no buffer de recebimento do firmware interno da base antes que a ordem de trava de motores sobressaia.

> [!IMPORTANT]
> **3. Necessidade do Modal de Bloqueio Durante a Reinicialização (`RebootOverlayModal`)**:
> Por conta dos tempos de estabilização do hardware (~5 a 8 segundos para reiniciar a porta serial, subir o servidor de vídeo e aquecer as ações do MoveIt ROS 2), a interface web exibe um **Popup Modal de Bloqueio em Tela Cheia** com barra de progresso e checklist dinâmico. O acesso a botões e comandos fica **100% desabilitado** até que todos os 5 passos do boot passem na verificação de saúde.

---

### 🔄 Como Inicializar o Control Center

```bash
cd /home/future-lab/B002_Future_Lab_Bots/future_lab_control_center
docker compose down && docker compose up --build -d
```

Acesse no navegador: **`http://localhost:3000`** (Frontend) ou **`http://localhost:8000/docs`** (API REST Swagger).

