"""Maintain one aggregate operational incident on GitHub; never include logs."""
import json
import os
import subprocess

TITLE = 'Delivery service needs attention'
MARKER = '<!-- delivery-health-incident -->'


def gh(*args):
    return subprocess.check_output(['gh', *args], text=True).strip()


def reconcile(failed, run_url):
    issues = json.loads(gh('issue', 'list', '--state', 'open', '--search', f'{TITLE} in:title',
                           '--limit', '100', '--json', 'number,title,body,author'))
    incidents = [i for i in issues if i['title'] == TITLE and MARKER in i['body']
                 and i.get('author', {}).get('login') in ('github-actions[bot]', 'app/github-actions')]
    if failed:
        if not incidents:
            gh('issue', 'create', '--title', TITLE, '--body',
               f'{MARKER}\nScheduled delivery, preparation, webhook or overdue health check failed.\n\n'
               f'Run: {run_url}\n\nInspect the private dashboard and redacted workflow annotations. '
               'Do not force resend uncertain deliveries. This issue closes after a healthy scheduled run.')
    else:
        for issue in incidents:
            # Explicit issue number, never close unrelated/operator-created issues.
            gh('issue', 'close', str(issue['number']), '--comment', f'Health checks recovered: {run_url}')


if __name__ == '__main__':
    reconcile(os.environ['DELIVERY_RESULT'] != 'success', os.environ['DELIVERY_RUN_URL'])
