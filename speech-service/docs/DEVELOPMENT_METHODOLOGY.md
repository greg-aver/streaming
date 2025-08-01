# Методология разработки - Циклический подход

## 🔄 Основные принципы разработки

### **Золотое правило: Маленькие шаги + Полное тестирование + Частые коммиты**

```
Мелкая функция → Коммит → Тесты → Коммит → Исправления → Коммит → Пуш → Следующая функция
```

### **🔄 Git workflow как Python Senior Developer:**
- **Частые коммиты** на каждом логическом этапе
- **Понятные commit messages** с контекстом
- **Коммит ≠ Пуш** - коммитим локально часто, пушим при готовности
- **Использование git log** для отслеживания прогресса
- **Git как инструмент документирования** процесса разработки

## 📋 Циклическая методология

### **Цикл разработки (30-90 минут на итерацию):**

1. **Выбрать ОДНУ мелкую функцию**
   - Максимум 1-2 часа работы
   - Четко определённая задача
   - Один компонент или один аспект

2. **Реализовать функцию**
   - Следовать архитектурным принципам
   - Добавить необходимый код
   - Поддерживать чистоту кода

3. **Написать/обновить тесты**
   - Unit тесты для новой функции
   - Убедиться что старые тесты проходят
   - Покрытие новой функциональности

4. **Протестировать ВСЕ**
   - Запустить все существующие тесты
   - Убедиться что ничего не сломалось
   - Проверить интеграцию

5. **Серия КОММИТОВ по логическим этапам**
   - Коммит после реализации функции
   - Коммит после написания тестов  
   - Коммит после исправлений (если нужны)
   - Push в репозиторий только когда ВСЁ готово

6. **Документировать прогресс**
   - Обновить TESTING_LOG.md
   - Отметить выполненные задачи
   - Зафиксировать найденные проблемы

7. **Перейти к следующей мелкой функции**

## ⚠️ Критические правила

### **НИКОГДА НЕ НАРУШАТЬ:**

1. **Не делать большие изменения за раз**
   - Максимум 1-2 файла за итерацию
   - Одна функция = один коммит
   - Если изменений много - разбить на части

2. **Обязательно тестировать ВСЁ перед коммитом**
   - Все старые тесты должны проходить
   - Новые тесты должны проходить
   - Нет исключений!

3. **Коммитить только рабочий код**
   - Если что-то сломано - НЕ коммитить
   - Сначала исправить, потом коммитить
   - Коммиты = стабильные снапшоты

4. **Документировать каждый шаг**
   - Ведение TESTING_LOG.md
   - Понятные сообщения коммитов
   - Отслеживание прогресса

## 📊 Примеры итераций

### **✅ Правильная итерация:**
```
Итерация N: "Добавить Mock VAD Service"
1. Создать MockVADService класс (30 мин)
2. Написать 8 тестов для MockVADService (45 мин)
3. Запустить все тесты - ВСЁ проходит ✅
4. Коммит: "feat: add MockVADService with comprehensive tests"
5. Push + документирование в TESTING_LOG.md
ИТОГО: 90 минут, стабильный результат
```

### **❌ Неправильная итерация:**
```
Итерация N: "Реализовать всю VAD систему"
1. Создать VADService + VADWorker + тесты + интеграцию (4 часа)
2. Множество проблем, тесты не проходят
3. Попытки исправить всё сразу
4. Потеря контроля над изменениями
5. Коммит не делается, прогресс теряется
ИТОГО: 4+ часов, нестабильный результат
```

## 🎯 Текущее применение методологии

### **Итерация 1 (ЗАВЕРШЕНА ✅):**
- Базовые компоненты: Config, Events, Models
- 33/33 теста прошли
- Стабильный коммит сделан

### **Итерация 2 (В ПРОЦЕССЕ 🔄):**
- Mock VAD Service ✅ (12 тестов)
- Mock ASR Service 🔄 (17 тестов создано)
- Mock Diarization Service ⏳

### **Планируемые итерации:**
- Итерация 3: Workers тестирование
- Итерация 4: Интеграционные тесты
- Итерация 5: WebSocket интеграция

## 📝 Шаблон планирования итерации

```markdown
### Итерация N: "[Название одной функции]"
**Время**: [дата начала]
**Цель**: [четкая, измеримая цель]
**Файлы**: [какие файлы будут изменены]

**План (60-90 минут):**
1. [Конкретная задача 1] - [время]
2. [Конкретная задача 2] - [время]  
3. [Тестирование] - [время]
4. [Документирование] - [время]

**Критерии готовности:**
- [ ] Функция реализована
- [ ] Тесты написаны и проходят
- [ ] Все старые тесты проходят
- [ ] Документация обновлена
- [ ] Коммит сделан

**Результат**: [что получили по факту]
```

## 🚀 Преимущества методологии

1. **Контролируемый прогресс** - всегда знаем где находимся
2. **Стабильность** - каждый коммит = рабочая версия
3. **Отладка** - легко найти где что сломалось
4. **Мотивация** - частые успешные завершения
5. **Качество** - тщательное тестирование каждого шага
6. **Документированность** - полная история разработки

## 🔧 Git Workflow для Python Senior Developer

### **Стратегия коммитов:**

```bash
# Пример итерации: "Добавить Mock ASR Service"

# 1. Создаём функцию
git add app/services/asr_service.py
git commit -m "feat: implement MockASRService class with basic structure"

# 2. Пишем тесты
git add tests/test_asr_service.py  
git commit -m "test: add comprehensive tests for MockASRService (17 tests)"

# 3. Исправляем найденные проблемы (если есть)
git add app/services/asr_service.py
git commit -m "fix: correct confidence calculation in MockASRService"

# 4. Финальная проверка и документация
git add TESTING_LOG.md
git commit -m "docs: update testing log with ASR service results"

# 5. Push когда ВСЁ готово
git push origin feature/testing-iteration-2-services
```

### **Типы коммитов (Conventional Commits):**
- `feat:` - новая функция
- `test:` - добавление/изменение тестов
- `fix:` - исправление багов
- `docs:` - изменения в документации
- `refactor:` - рефакторинг кода
- `style:` - форматирование кода
- `chore:` - обновление зависимостей, конфигурации

### **Когда делать коммит:**
1. ✅ **После создания функции/класса** (даже если не полностью готов)
2. ✅ **После написания тестов** 
3. ✅ **После исправления багов**
4. ✅ **После обновления документации**
5. ✅ **После любого логически завершённого этапа**

### **Когда делать push:**
- 🔄 **После завершения полной итерации** (все тесты проходят)
- 🔄 **Когда функция полностью готова и протестирована**
- 🔄 **В конце рабочего дня** (для сохранности)

### **Контроль прогресса через Git:**
```bash
# Посмотреть последние коммиты
git log --oneline -10

# Посмотреть изменения в итерации
git log --oneline feature/testing-iteration-2-services ^main

# Статистика коммитов
git shortlog -s -n
```

## ⚡ Инструменты поддержки

- **docs/CURRENT_STATUS.md** - АКТУАЛЬНОЕ состояние проекта (ГДЕ МЫ, ЧТО ДЕЛАЕМ, КУДА ИДЕМ)
- **TESTING_LOG.md** - детальный лог всех итераций
- **TODO.md** - планирование задач  
- **Git коммиты** - детальная история каждого шага
- **Git branches** - изоляция итераций
- **pytest** - автоматизированное тестирование

---

**Помни**: Медленно и стабильно = быстрее в долгосрочной перспективе!

**Дата создания**: 2025-08-02  
**Статус**: ОБЯЗАТЕЛЬНАЯ К ПРИМЕНЕНИЮ методология