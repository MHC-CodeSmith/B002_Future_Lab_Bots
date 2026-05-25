# B002 Future Lab Bots

Repositorio agregador para manter juntos os tres projetos do laboratorio B002.

## Estrutura

```text
B002_Future_Lab_Bots/
  integration_cobot_tb4/  # visualizacao 3D, overlay e ponte MyCobot/TB4
  turtlebot4_jazzy/       # TurtleBot4 Jazzy, mapas B002, Nav2 e rotinas
  cobot/                  # MyCobot, MoveIt, mock e tooling do braco
```

Cada pasta acima e um submodulo Git. Os commits reais continuam nos repositorios
originais; este repositorio salva quais versoes dos tres devem andar juntas.

## Clonar tudo

```bash
git clone --recurse-submodules git@github.com:MHC-CodeSmith/B002_Future_Lab_Bots.git
cd B002_Future_Lab_Bots
```

Se ja clonou sem submodulos:

```bash
git submodule update --init --recursive
```

## Atualizar submodulos

```bash
git submodule update --remote --merge
git status
git commit -am "Update project submodule revisions"
git push
```

## Execucao rapida

Visualizacao 3D:

```bash
cd integration_cobot_tb4
source /opt/ros/jazzy/setup.bash
./scripts/run_3d_view.sh
```

TurtleBot4 Jazzy:

```bash
cd turtlebot4_jazzy
./run_lab_world.sh false false 0.0 0.0 0.0
```

MyCobot:

```bash
cd cobot
./mycobot_docker/RUN_PLANNING_PC.sh
```

Os diretorios antigos em `/home/mhc/Germany/cobot_tb4_integration`,
`/home/mhc/Germany/turtlebot4_jazzy` e `/home/mhc/Germany/Cobot` continuam
existindo e continuam funcionando.
