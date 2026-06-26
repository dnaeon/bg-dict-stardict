# Български тълковен речник в StarDict формат

Български тълковен речник в `StarDict` формат, генериран от базата данни на
[Речко](https://rechnik.chitanka.info/about).

Подходящ за [KOReader](https://github.com/koreader/koreader),
[GoldenDict](https://github.com/goldendict/goldendict) и
[GoldenDict-ng](https://github.com/xiaoyifang/goldendict-ng),
[AARD2](https://github.com/itkach/aard2-android),
[sdcv](https://github.com/Dushistov/sdcv) и всеки друг четец, който поддържа
StarDict.

## Инсталация

1. Изтеглете архива `bulgarian-stardict.zip` от секцията Releases на това
   хранилище, или го генерирайте сами по инструкциите по-долу.
2. Разархивирайте го. Ще получите папка `bulgarian` със следните файлове:
   - `bulgarian.ifo`
   - `bulgarian.idx`
   - `bulgarian.dict.dz`
   - `bulgarian.syn`
3. Копирайте цялата папка `bulgarian` в директорията с речници на вашия четец:
   - **KOReader** (Kindle): `koreader/data/dict/`
   - **KOReader** (Kobo): `.adds/koreader/data/dict/`
   - **KOReader** (PocketBook): `applications/koreader/data/dict/`
   - **KOReader** (Android): `/sdcard/koreader/data/dict/`
   - **KOReader** (Linux): `$HOME/.config/koreader/data/dict/`
   - **KOReader** (macOS): `$HOME/Library/Application Support/koreader/data/dict/`
   - **GoldenDict**: добавете директорията през `Edit > Dictionaries > Sources > Files`.
   - **AARD2**: копирайте папката в директорията с речници на устройството и я добавете през менюто на приложението.
4. Стартирайте четеца. При маркиране на дума ще получите тълкуване от речника.

## Преинсталиране

Ако обновявате речника, изтрийте старата папка `bulgarian` от директорията с
речници, преди да копирате новата.

## Изграждане на речника

Изграждането става локално, без да се клонира друго хранилище и без да се сваля
нищо от Интернет - изходните данни се намират в `vendor/db.sqlite` и са част от
това хранилище.

### Изграждане чрез Docker (препоръчително)

Инсталирайте [Docker](https://docs.docker.com/get-docker/) на вашата машина.

След това всяко от следните `make` извиквания изпълнява съответната операция
вътре в Docker контейнер, без да е нужно да инсталирате нищо друго на хост
машината:

``` shell
make docker-all       # изграждане, проверка и пакетиране
make docker-build     # само изграждане
make docker-verify    # само проверка
make docker-package   # само пакетиране
```

Под капака тези цели извикват скрипта `scripts/docker-run.sh`, който построява
Docker образа при първото стартиране (около 2 минути) и след това стартира
кеширан. Скриптът може да се извика и директно за други операции, които нямат
отделна make цел - например при обновяване на дъмпа на "Речко":

``` shell
./scripts/docker-run.sh make refresh-db DUMP=/work/db.sql
```

(Файлът `db.sql` трябва да бъде поставен в директорията на хранилището, за да
бъде видим на пътя `/work/db.sql` вътре в контейнера.)

### Изграждане без Docker

Алтернативен начин - инсталиране на инструментите директно на хост машината.

#### Изисквания

1. `python3`, версия 3.13 или по-нова
2. Следните Python пакети:
   - `pyglossary`
   - `python-idzip`
3. `make`
4. `xz`
5. `zip`
6. `sdcv` (използван само за проверка на речника)

На macOS чрез Homebrew:

``` shell
brew install python make xz zip sdcv
```

На Debian:

``` shell
sudo apt-get install python3 python3-pip make xz-utils zip sdcv
```

На Arch Linux:

```
sudo pacman -S python make xz zip sdcv
```

Инсталация на Python пакетите:

```
pip3 install --user pyglossary python-idzip
```

Или във виртуална среда:

```
python3 -m venv .venv
source .venv/bin/activate
pip install pyglossary python-idzip
```

## Команди

Всички операции се изпълняват през `make`:

| Команда                               | Какво прави                                                                  |
|---------------------------------------|------------------------------------------------------------------------------|
| `make build`                          | Изгражда StarDict речника от `vendor/db.sqlite` в `out/stardict/bulgarian/`. |
| `make verify`                         | Проверка на генерирания речник чрез `sdcv`.                                  |
| `make package`                        | Пакетира готовия речник в `dist/bulgarian-stardict.zip`.                     |
| `make test`                           | Изпълнява тестове                                                            |
| `make all`                            | Изпълнява build, verify и package последователно.                            |
| `make clean`                          | Изтрива `out/` (не пипа `vendor/db.sqlite`).                                 |
| `make distclean`                      | `clean` плюс изтриване на `dist/`.                                           |
| `make refresh-db DUMP=path/to/db.sql` | Обновява `vendor/db.sqlite` от нов MySQL дъмп.                               |
| `make docker-all`                     | Същото като `make all`, но изпълнено вътре в Docker контейнер.               |
| `make docker-build`                   | Същото като `make build`, но в Docker.                                       |
| `make docker-verify`                  | Същото като `make verify`, но в Docker.                                      |
| `make docker-package`                 | Същото като `make package`, но в Docker.                                     |

Пример за пълно изграждане:

```
make all
```

## Обновяване от нов изходен дъмп

Дъмпът на "Речко" се намира на `https://rechnik.chitanka.info/db.sql.gz`. Към
момента на писане на това README той е замразен на 22 октомври 2013 г. (вижте
`vendor/README.md` за подробности). Ако chitanka публикуват нова версия:

```
curl -O https://rechnik.chitanka.info/db.sql.gz
gunzip db.sql.gz
make refresh-db DUMP=./db.sql
make all
```

Това ще регенерира `vendor/db.sqlite` от новия дъмп, ще изгради речника, ще го
провери и ще го пакетира.

## Източници и благодарности

Това хранилище не съдържа никакво оригинално речниково съдържание. То само
преобразува вече съществуваща база данни в подходящ за StarDict четци
формат.

Цялата заслуга за съдържанието принадлежи на следните проекти:

- [Речко](https://rechnik.chitanka.info/about) (rechnik.chitanka.info),
  универсален български тълковен речник, поддържан от общността около
  [chitanka.info](https://chitanka.info/). Това е първоизточникът за този
  речник.
- [chitanka/rechko](https://github.com/chitanka/rechko) е софтуерът зад Речко
- [yanosh-k/bulgarian_dictionary](https://github.com/yanosh-k/bulgarian_dictionary)
  преобразува SQL дъмпа на "Речко" в Kindle MOBI речник. Този проект
  първоначално използваше техния OPF/HTML като източник; в момента не зависи
  пряко от това хранилище, но скриптът `scripts/format_meaning.py` е Python
  препис на тяхната функция `format_meaning()` от `convertors/db_to_jsonl.php` и
  наследява всички решения за рендериране.

## Лиценз

Съдържанието на речника е производно на базата данни на "Речко". Моля, спазвайте
оригиналните условия за ползване, посочени на
[rechnik.chitanka.info/about](https://rechnik.chitanka.info/about).
