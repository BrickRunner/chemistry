import sqlite3
import os

# Инициализация базы данных и создание таблиц при первом запуске
def init_db():
    # Подключение к базе данных (создается файл database.db)
    conn = sqlite3.connect("database.db")
    cursor = conn.cursor()

    # Таблица тем с возможными файлами по каждой теме
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS topics (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            section TEXT,  -- Раздел химии (Органическая, Неорганическая и т.д.)
            topic TEXT,    -- Название темы
            theory_file TEXT,  -- Имя файла с теорией
            task_file TEXT,    -- Имя файла с заданием
            homework_file TEXT -- Имя файла с домашним заданием
        )
    ''')

    # Таблица файлов (не используется в текущем коде, но может использоваться для хранения файлов отдельно)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS files (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            topic_id INTEGER NOT NULL,     -- Внешний ключ на тему
            file_type TEXT NOT NULL,       -- Тип файла (теория, задание, домашка)
            file_path TEXT NOT NULL,       -- Путь к файлу
            FOREIGN KEY (topic_id) REFERENCES topics(id)
        )
    """)
    
    conn.commit()
    conn.close()

# Инициализируем базу данных
init_db() 
print("База данных и таблицы успешно созданы.")


# Возвращает список доступных разделов химии
def get_sections():
    return ['Органическая химия', 'Неорганическая химия', 'Общая химия']


# Получает список тем в выбранном разделе, у которых есть хотя бы один прикреплённый файл
def get_topics_by_section(section):
    conn = sqlite3.connect("database.db")
    cursor = conn.cursor()
    
    cursor.execute("""
        SELECT topic FROM topics 
        WHERE section = ? AND (
            theory_file IS NOT NULL OR 
            task_file IS NOT NULL OR 
            homework_file IS NOT NULL
        )
    """, (section,))
    
    # Преобразуем результат выборки в список тем
    topics = [row[0] for row in cursor.fetchall()]
    conn.close()
    return topics


# Получает список файлов по теме (теория, задание, домашка)
def get_files_for_topic(topic):
    conn = sqlite3.connect("database.db")
    cursor = conn.cursor()

    cursor.execute("SELECT theory_file, task_file, homework_file FROM topics WHERE topic = ?", (topic,))
    files = cursor.fetchone()
    conn.close()
    return files


# Удаляет указанный файл по типу (Теория, Задание, Домашнее задание) из определенной темы
def delete_file_by_type(section: str, topic: str, file_type: str) -> str:
    """
    Удаляет файл заданного типа (Теория, Задание, Домашнее задание) из темы.
    Возвращает результат операции: 
    'deleted' - файл удален,
    'not_found' - файл не найден,
    'no_topic' - тема не найдена,
    'topic_removed' - тема удалена, т.к. не осталось других файлов
    """

    # Соответствие типов файлов столбцам в таблице
    column_map = {
        "Теория": "theory_file",
        "Задание": "task_file",
        "Домашнее задание": "homework_file"
    }

    # Получаем нужное имя столбца
    column = column_map.get(file_type)
    if not column:
        return "not_found"

    conn = sqlite3.connect("database.db")
    cursor = conn.cursor()

    # Получаем путь к файлу и наличие других файлов в теме
    cursor.execute(f"SELECT {column}, theory_file, task_file, homework_file FROM topics WHERE section = ? AND topic = ?", (section, topic))
    row = cursor.fetchone()

    if not row:
        conn.close()
        return "no_topic"

    file_to_delete, theory, task, hw = row

    # Если файла указанного типа нет
    if not file_to_delete:
        conn.close()
        return "not_found"

    # Удаление файла с диска, если он существует
    file_path = f"files/{file_to_delete}"
    if os.path.exists(file_path):
        os.remove(file_path)

    # Обнуляем соответствующий столбец в базе данных
    cursor.execute(f"UPDATE topics SET {column} = NULL WHERE section = ? AND topic = ?", (section, topic))
    conn.commit()

    # Проверяем, остались ли другие файлы по этой теме
    cursor.execute("SELECT theory_file, task_file, homework_file FROM topics WHERE section = ? AND topic = ?", (section, topic))
    theory, task, hw = cursor.fetchone()

    # Если все три типа файлов отсутствуют — удаляем тему
    if not theory and not task and not hw:
        cursor.execute("DELETE FROM topics WHERE section = ? AND topic = ?", (section, topic))
        conn.commit()
        conn.close()
        return "topic_removed"

    conn.close()
    return "deleted"
