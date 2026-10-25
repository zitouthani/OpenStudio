const phases = [
  {
    title: "Cadrage et architecture",
    description: "Définir la direction, les fondations et la feuille de route.",
    tasks: [
      "Vision produit et objectifs",
      "Architecture et frontières des modules",
      "Périmètre initial et feuille de route",
      "Sécurité, licences et stratégie de test",
    ],
  },
  {
    title: "Fondations",
    description: "Poser le modèle des tâches, le moteur et les premiers flux de données.",
    tasks: [
      "Modèle de tâche versionné et validation",
      "Graphe d’exécution",
      "Composants de lecture, filtrage, transformation et écriture CSV",
      "Tests de bout en bout du flux principal",
    ],
  },
  {
    title: "Éditeur visuel",
    description: "Permettre de concevoir et de piloter les flux depuis une interface.",
    tasks: [
      "Fenêtre principale et palette de composants",
      "Éditeur graphique et panneau de propriétés",
      "Enregistrement et chargement des tâches",
      "Validation des liens et exécution depuis l’interface",
    ],
  },
  {
    title: "Exécution fiable",
    description: "Rendre l’exécution prévisible, résiliente et efficace en mémoire.",
    tasks: [
      "Traitement en lots et flux continus",
      "Gestion de la pression des files d’attente",
      "Erreurs structurées, reprises et annulation",
      "Tests de mémoire et de performance",
    ],
  },
  {
    title: "Connecteurs",
    description: "Étendre les sources et destinations tout en protégeant les paramètres.",
    tasks: [
      "Connecteurs fichiers et CSV",
      "Prise en charge de PostgreSQL et MySQL",
      "Intégration des API REST",
      "Stockage objet et gestion sécurisée des accès",
    ],
  },
  {
    title: "Interopérabilité et publication",
    description: "Préparer les échanges de données et une première version distribuable.",
    tasks: [
      "Analyse des formats de tâches externes",
      "Modèle intermédiaire et règles de conversion",
      "Rapport de couverture et limites identifiées",
      "Packaging, vérifications de licence et documentation",
    ],
  },
];

const storageKey = "openstudio-etl-progress-v1";
const statuses = [
  { value: "todo", label: "À faire" },
  { value: "in_progress", label: "En cours" },
  { value: "done", label: "Terminé" },
];

function showStorageError() {
  document.querySelector("#storage-status").classList.add("storage-error");
  document.querySelector("#storage-label").textContent = "Enregistrement indisponible";
}

function loadProgress() {
  try {
    const stored = localStorage.getItem(storageKey);
    const progress = stored ? JSON.parse(stored) : {};
    return progress && typeof progress === "object" && !Array.isArray(progress) ? progress : {};
  } catch (error) {
    console.error("Impossible de lire l’avancement enregistré.", error);
    showStorageError();
    return {};
  }
}

let progress = loadProgress();

function saveProgress() {
  try {
    localStorage.setItem(storageKey, JSON.stringify(progress));
  } catch (error) {
    console.error("Impossible d’enregistrer l’avancement dans ce navigateur.", error);
    showStorageError();
  }
}

function getTaskStatus(phaseIndex, taskIndex) {
  const status = progress[`${phaseIndex}-${taskIndex}`];
  return statuses.some((option) => option.value === status) ? status : "todo";
}

function updateSummary() {
  const taskStatuses = phases.flatMap((phase, phaseIndex) =>
    phase.tasks.map((_, taskIndex) => getTaskStatus(phaseIndex, taskIndex)),
  );
  const completed = taskStatuses.filter((status) => status === "done").length;
  const active = taskStatuses.filter((status) => status === "in_progress").length;
  const percentage = Math.round((completed / taskStatuses.length) * 100);
  const progressBar = document.querySelector("#progress-bar");

  document.querySelector("#progress-value").textContent = percentage;
  document.querySelector("#completed-count").textContent = completed;
  document.querySelector("#active-count").textContent = active;
  document.querySelector("#task-count").textContent = taskStatuses.length;
  document.querySelector("#phase-count").textContent = phases.length;
  document.querySelector("#progress-caption").textContent =
    `${completed} tâche${completed === 1 ? "" : "s"} terminée${completed === 1 ? "" : "s"} sur ${taskStatuses.length}`;
  progressBar.setAttribute("aria-valuenow", String(percentage));
  progressBar.querySelector("span").style.width = `${percentage}%`;

  phases.forEach((phase, phaseIndex) => {
    const done = phase.tasks.filter((_, taskIndex) => getTaskStatus(phaseIndex, taskIndex) === "done").length;
    document.querySelector(`#phase-progress-${phaseIndex}`).textContent =
      `${done}/${phase.tasks.length} terminée${done === 1 ? "" : "s"}`;
  });
}

function renderPhases() {
  const phaseList = document.querySelector("#phase-list");

  phases.forEach((phase, phaseIndex) => {
    const card = document.createElement("article");
    card.className = "phase-card";

    const header = document.createElement("div");
    header.className = "phase-header";

    const number = document.createElement("span");
    number.className = "phase-number";
    number.textContent = String(phaseIndex).padStart(2, "0");
    number.setAttribute("aria-hidden", "true");

    const titleWrap = document.createElement("div");
    titleWrap.className = "phase-title-wrap";

    const title = document.createElement("h3");
    title.className = "phase-title";
    title.textContent = `Phase ${phaseIndex} — ${phase.title}`;

    const description = document.createElement("p");
    description.className = "phase-description";
    description.textContent = phase.description;
    titleWrap.append(title, description);

    const phaseProgress = document.createElement("span");
    phaseProgress.className = "phase-progress";
    phaseProgress.id = `phase-progress-${phaseIndex}`;

    header.append(number, titleWrap, phaseProgress);

    const taskList = document.createElement("ul");
    taskList.className = "task-list";

    phase.tasks.forEach((task, taskIndex) => {
      const item = document.createElement("li");
      const row = document.createElement("div");
      row.className = "task-row";

      const label = document.createElement("span");
      label.className = "task-label";
      label.dataset.status = getTaskStatus(phaseIndex, taskIndex);

      const marker = document.createElement("span");
      marker.className = "task-marker";
      marker.setAttribute("aria-hidden", "true");

      const taskText = document.createElement("span");
      taskText.className = "task-text";
      taskText.textContent = task;
      label.append(marker, taskText);

      const select = document.createElement("select");
      select.className = "task-status";
      select.dataset.status = getTaskStatus(phaseIndex, taskIndex);
      select.setAttribute("aria-label", `Statut : ${task}`);
      statuses.forEach((status) => {
        const option = document.createElement("option");
        option.value = status.value;
        option.textContent = status.label;
        select.append(option);
      });
      select.value = getTaskStatus(phaseIndex, taskIndex);
      select.addEventListener("change", () => {
        const key = `${phaseIndex}-${taskIndex}`;
        progress[key] = select.value;
        label.dataset.status = select.value;
        select.dataset.status = select.value;
        saveProgress();
        updateSummary();
      });

      row.append(label, select);
      item.append(row);
      taskList.append(item);
    });

    card.append(header, taskList);
    phaseList.append(card);
  });
}

document.querySelector("#reset-progress").addEventListener("click", () => {
  if (!window.confirm("Réinitialiser tous les statuts de tâches ? Cette action est définitive.")) {
    return;
  }

  progress = {};
  saveProgress();
  document.querySelector("#phase-list").replaceChildren();
  renderPhases();
  updateSummary();
});

renderPhases();
updateSummary();
