
运行示例
```sh
# 试跑 3 条
python search_snapshot.py --input-file=/Users/eric/dev/working/email-url/emails.xlsx --sheet=Sheet1 --search-columns="G*" --rows=2-4

# 全部
python search_snapshot.py --input-file=/Users/eric/dev/working/email-url/emails.xlsx --sheet=Sheet1 --search-columns="G*" --rows=2+

python search_snapshot.py \
    --input-file=/Users/eric/dev/working/email-url/emails.xlsx \
    --sheet=Sheet1 \
    --search-columns='G*' \
    --rows=2+ \
    --debug
```