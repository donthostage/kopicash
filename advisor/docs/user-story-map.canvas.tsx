import {
  Callout,
  Divider,
  Grid,
  H1,
  H2,
  H3,
  Pill,
  Row,
  Stack,
  Stat,
  Table,
  Text,
  useHostTheme,
} from "cursor/canvas";

type State = "есть" | "частично" | "нет";

type Story = {
  text: string;
  state: State;
};

type Activity = {
  name: string;
  goal: string;
  stories: Story[];
};

const ACTIVITIES: Activity[] = [
  {
    name: "Войти",
    goal: "Открыть свой кошелёк",
    stories: [
      { text: "Экран приветствия и кошелёк", state: "есть" },
      { text: "Регистрация и вход по логину", state: "есть" },
      { text: "Тема луной и настройки справа", state: "есть" },
      { text: "Сессия кончилась — вернуться ко входу", state: "есть" },
    ],
  },
  {
    name: "Собрать карты",
    goal: "Видеть свои карты",
    stories: [
      { text: "Листать карты веером", state: "есть" },
      { text: "Добавить и удалить карту", state: "есть" },
      { text: "Удаление забирает и кешбэк карты", state: "есть" },
      { text: "Каталог из 30 банков старого экрана", state: "нет" },
    ],
  },
  {
    name: "Уже выбрал в банке",
    goal: "Зафиксировать действующие категории",
    stories: [
      { text: "Строки как в банке: «Кино» отдельно от «Афиши»", state: "есть" },
      { text: "Черновик снимка без записи в базу", state: "есть" },
      { text: "Поправить, добавить, убрать и подтвердить", state: "есть" },
      { text: "«На все покупки» — запасное правило этой карты", state: "есть" },
      { text: "Снимок читает модель только при ключе", state: "частично" },
    ],
  },
  {
    name: "Оплатить",
    goal: "Понять, какой картой платить",
    stories: [
      { text: "Категория, сумма и живой расчёт", state: "есть" },
      { text: "Точная категория важнее «на все»", state: "есть" },
      { text: "Правила не складываются", state: "есть" },
      { text: "Порог и округление считаются отдельно", state: "есть" },
      { text: "Повторный клик не пишет покупку дважды", state: "есть" },
      { text: "MCC и исключения банка", state: "нет" },
    ],
  },
  {
    name: "Ещё ничего не выбрал",
    goal: "Решить, что включить на месяц",
    stories: [
      { text: "Предложения не меняют сегодняшнюю покупку", state: "есть" },
      { text: "План по истории или введённым тратам", state: "есть" },
      { text: "Прирост в рублях и занятые места", state: "есть" },
      { text: "Включение только после «Я выбрал это в банке»", state: "есть" },
      { text: "Несколько банков: в тесте да, в браузере один", state: "частично" },
      { text: "Ограниченный перебор честно пишет «приблизительно»", state: "есть" },
    ],
  },
  {
    name: "Сверить месяц",
    goal: "Увидеть, сколько вышло",
    stories: [
      { text: "Покупки, лучшая карта и недобор", state: "есть" },
      { text: "Сравнение с обычной картой", state: "есть" },
      { text: "Короткий разбор месяца", state: "есть" },
      { text: "Общебанковский потолок сверх лимита строки", state: "нет" },
    ],
  },
];

const TONE: Record<State, "success" | "warning" | "neutral"> = {
  есть: "success",
  частично: "warning",
  нет: "neutral",
};

function Column({ activity }: { activity: Activity }) {
  const theme = useHostTheme();
  return (
    <Stack gap={8} style={{ width: 220, flex: "0 0 220px" }}>
      <Stack gap={2}>
        <H3>{activity.name}</H3>
        <Text size="small" tone="secondary">
          {activity.goal}
        </Text>
      </Stack>
      {activity.stories.map((story) => (
        <Stack
          key={story.text}
          gap={6}
          style={{
            padding: "8px 10px",
            border: `1px solid ${theme.stroke.tertiary}`,
            borderLeft: `3px solid ${
              story.state === "есть"
                ? theme.accent.primary
                : story.state === "частично"
                  ? theme.text.secondary
                  : theme.stroke.primary
            }`,
            background: theme.bg.elevated,
          }}
        >
          <Text size="small">{story.text}</Text>
          <Pill tone={TONE[story.state]} size="sm" active={story.state === "есть"}>
            {story.state}
          </Pill>
        </Stack>
      ))}
    </Stack>
  );
}

export default function UserStoryMap() {
  const done = ACTIVITIES.reduce(
    (count, activity) => count + activity.stories.filter((story) => story.state === "есть").length,
    0,
  );
  const open = ACTIVITIES.reduce(
    (count, activity) => count + activity.stories.filter((story) => story.state !== "есть").length,
    0,
  );

  return (
    <Stack gap={20}>
      <Stack gap={6}>
        <H1>Карта сценария «Советник»</H1>
        <Text tone="secondary">
          Человек с несколькими картами решает две задачи: какой картой платить сейчас и какие категории включить в банке на следующий месяц. Снимок сам ничего не включает.
        </Text>
      </Stack>

      <Grid columns={3} gap={16}>
        <Stat value={String(done)} label="Историй уже в кошельке" tone="success" />
        <Stat value={String(open)} label="Ещё не закрыто целиком" tone="warning" />
        <Stat value="+100 ₽" label="План: «Кино» 2000 ₽, сейчас 0 ₽" />
      </Grid>

      <Stack gap={8}>
        <H2>Путь слева направо</H2>
        <Text size="small" tone="tertiary">
          Сверху — шаг человека. Ниже — истории этого шага. Источник: кошелёк на main, 21 ноября 2026.
        </Text>
        <Row gap={12} align="start" style={{ overflowX: "auto", paddingBottom: 4 }}>
          {ACTIVITIES.map((activity) => (
            <Column key={activity.name} activity={activity} />
          ))}
        </Row>
      </Stack>

      <Divider />

      <H2>Две развилки одного расчёта</H2>
      <Grid columns={2} gap={16}>
        <Callout tone="success" title="Уже выбрал в банке">
          Черновик или ручной ввод, правка каждой строки, затем «Подтвердить подключение в банке». Эти строки участвуют в совете перед покупкой.
        </Callout>
        <Callout tone="info" title="Ещё ничего не выбрал">
          Предложения нескольких банков сохраняются отдельно. План сравнивает их с тратами и свободными местами. В покупку они попадают только после подтверждения, что выбор уже сделан в банке.
        </Callout>
      </Grid>

      <Stack gap={8}>
        <H2>Кейс и граница продукта</H2>
        <Table
          headers={["Кейс", "Что есть", "Граница"]}
          columnAlign={["left", "left", "left"]}
          rowTone={["success", "success", "success", "success", "warning", "warning", "neutral", "neutral"]}
          rows={[
            ["«Кино» и «Афиша в городе»", "Две разные строки", "Не схлопываются в «Развлечения»"],
            ["«На все покупки»", "Запасное правило одной карты", "Не общий 1% на все банки"],
            ["Точная категория и fallback", "Берётся одно правило", "Проценты не складываются"],
            ["99,99 ₽ и 100 ₽", "Порог в копейках", "Результаты разные, если правило так задано"],
            ["Несколько банков в плане", "Расчёт и тесты", "В браузере проверен один банк"],
            ["Снимок условий", "Черновик, потом подтверждение", "Модель только при ключе"],
            ["MCC и исключения банка", "Лимит конкретной строки", "Правила банка сами не выводятся"],
            ["Выкладка на staging", "main опубликован", "Защита CI ещё смотрит старый экран"],
          ]}
        />
        <Text size="small" tone="tertiary">
          Пример плана снят в браузере на временной базе: сейчас 0,00 ₽, по плану 100,00 ₽, разница 100,00 ₽.
        </Text>
      </Stack>
    </Stack>
  );
}
