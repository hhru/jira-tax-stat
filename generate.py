# coding: utf-8

import urllib2
import json
import base64
import itertools
import time
from collections import namedtuple, OrderedDict

import jinja2

import config

compact_issue = namedtuple('issue',
                           ('key', 'summary', 'team', 'sp', 'is_business', 'is_backend', 'is_frontend', 'is_backfront'))
team_summary = namedtuple('summary', ('team', 'business', 'tax', 'backend', 'frontend', 'backfront'))

ctx = {'time': time.strftime("%a, %d %b %Y %H:%M")}

template = jinja2.Environment(
    loader=jinja2.FileSystemLoader(config.absolute_path),
    trim_blocks=True,
    autoescape=True,
    lstrip_blocks=True
).get_template('template.jinja2')


def get_filter():
    response = json_by_url('https://{}/rest/api/2/filter/{}'.format(config.host, config.filter_id))
    return response['searchUrl'] + '&maxResults=999', response['viewUrl']


def json_by_url(url):
    print 'requesting {}'.format(url)
    request = urllib2.Request(url)
    request.add_header('Authorization',
                       'Basic {0}'.format(base64.b64encode('{0}:{1}'.format(config.username, config.password))))
    t = time.time()
    res = urllib2.urlopen(request)
    print time.time() - t
    print 'got {}'.format(res.getcode())
    return json.loads(res.read())


def compact(issue):
    _fields = issue['fields']
    _labels = _fields['labels']

    team = _fields['customfield_10961']['value']
    sp = _fields['customfield_11212']
    summary = _fields['summary']
    issue = issue['key']
    is_business = 'tax' not in _labels
    is_backend = 'tax' in _labels and 'frontend' not in _labels
    is_frontend = 'tax' in _labels and 'frontend' in _labels and 'backend' not in _labels
    is_backfront = 'tax' in _labels and 'frontend' in _labels and 'backend' in _labels

    return compact_issue(issue, summary, team, sp, is_business, is_backend, is_frontend, is_backfront)


def calc_percents(team_summary):
    total = team_summary.business + team_summary.tax
    percent = lambda x: int(round(x / total * 100)) if total > 0 else 0
    return percent(team_summary.business), percent(team_summary.tax), percent(team_summary.backend), percent(
        team_summary.frontend), percent(team_summary.backfront)


def calc_avg(teams):
    avg = lambda k: int(sum(map(lambda i: i[k], teams)) / float(len(teams)))
    return avg(0), avg(1), avg(2), avg(3), avg(4)


def gen_summaries(issues_by_team):
    for group in issues_by_team:
        business = 0
        tax = 0
        backend = 0
        frontend = 0
        backfront = 0
        for issue in group[1]:
            if issue.sp is None:
                print 'skipped ', issue.key
                continue
            business += issue.sp if issue.is_business else 0
            tax += issue.sp if not issue.is_business else 0
            backend += issue.sp if issue.is_backend else 0
            frontend += issue.sp if issue.is_frontend else 0
            backfront += issue.sp if issue.is_backfront else 0
        yield team_summary(group[0], business, tax, backend, frontend, backfront)


def group_by_type(issues_by_team):
    result = {}

    for group in issues_by_team:
        result[group[0]] = {
            'business': filter(lambda i: i.is_business, group[1]),
            'backend': filter(lambda i: i.is_backend, group[1]),
            'frontend': filter(lambda i: i.is_frontend, group[1]),
            'backfront': filter(lambda i: i.is_backfront, group[1])
        }

    return result


def get_totals(issues_by_team):
    acc_backend = []
    acc_frontend = []
    acc_backfront = []

    for group in issues_by_team:
        acc_backend.extend(filter(lambda i: i.is_backend, group[1]))
        acc_frontend.extend(filter(lambda i: i.is_frontend, group[1]))
        acc_backfront.extend(filter(lambda i: i.is_backfront, group[1]))

    return acc_backend, acc_frontend, acc_backfront


def group_issues_by_team(issues):
    grouping_key = lambda i: i.team
    return [(k, list(g)) for k, g in itertools.groupby(sorted(issues, key=grouping_key), key=grouping_key)]


def process(issues, url):
    compact_issues = map(compact, issues)

    compact_issues_by_team = group_issues_by_team(compact_issues)

    all_percents = []

    ctx['teams'] = {}
    ctx['sp_todo'] = {}
    ctx['filter_url'] = url

    for team_summary in gen_summaries(compact_issues_by_team):
        percents = calc_percents(team_summary)
        all_percents.append(percents)
        ctx['teams'][team_summary.team] = percents

    ctx['teams'] = OrderedDict(sorted(ctx['teams'].items()))
    ctx['avgs'] = calc_avg(all_percents)
    ctx['details'] = group_by_type(compact_issues_by_team)
    ctx['details'] = OrderedDict(sorted(ctx['details'].items()))
    #ctx['totals'] = get_totals(compact_issues_by_team)

    ctx['host'] = config.host

    return ctx


def get_html(ctx):
    return template.render(**ctx).encode('utf-8')


def get_json(ctx):
    return json.dumps(ctx['teams']).encode('utf-8')


_filter = get_filter()
data = process(issues=json_by_url(_filter[0])['issues'], url=_filter[1])

with open('{}/index.html'.format(config.absolute_path), 'w') as f:
    f.write(get_html(data))

with open('{}/index.json'.format(config.absolute_path), 'w') as f:
    f.write(get_json(data))

