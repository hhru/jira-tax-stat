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

ctx = {
    'time': time.strftime("%a, %d %b %Y %H:%M"),
    'default_tax_percent': config.default_tax_percent,
    'groups': config.groups,
}

template = jinja2.Environment(
    loader=jinja2.FileSystemLoader(config.absolute_path),
    trim_blocks=True,
    autoescape=True,
    lstrip_blocks=True
).get_template('template.jinja2')


def get_filter():
    response = json_by_url('https://{}/rest/api/2/filter/{}'.format(config.host, config.filter_id))
    return response['searchUrl'] + '&maxResults=9999', response['viewUrl']


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


def calc_avg(teams):
    avg = lambda k: int(sum(map(lambda i: i[k], teams)) / float(len(teams)))
    return avg(0), avg(1), avg(2), avg(3), avg(4)


def calculate_percent(sp, total_sp):
    return int(round(sp / total_sp * 100)) if total_sp > 0 else 0

def get_warning_level(current_percent, required_percent):
    levels = (
        ('blocker', int(round(required_percent * 0.7))),
        ('critical', int(round(required_percent * 0.8))),
        ('major', int(round(required_percent * 0.85)))
    )

    for level, value in levels:
        if current_percent <= value:
            return level

    return None

def gen_summaries(issues_by_team):
    for group in issues_by_team:
        business = 0
        tax = 0
        backend = 0
        frontend = 0
        backfront = 0

        tax_percent = config.default_tax_percent
        team = group[0]
        if team in config.custom_tax_percent:
            tax_percent = config.custom_tax_percent[team]

        for issue in group[1]:
            if issue.sp is None:
                print 'skipped ', issue.key
                continue
            business += issue.sp if issue.is_business else 0
            tax += issue.sp if not issue.is_business else 0
            backend += issue.sp if issue.is_backend else 0
            frontend += issue.sp if issue.is_frontend else 0
            backfront += issue.sp if issue.is_backfront else 0

        total = business + tax
        percent_tax = calculate_percent(tax, total)

        yield {
            'name': team,
            'percent_tax': percent_tax,
            'percent_backend': calculate_percent(backend, total),
            'percent_frontend': calculate_percent(frontend, total),
            'percent_dual': calculate_percent(backfront, total),
            'tax_percent': tax_percent,
            'is_custom_tax_percent': tax_percent != config.default_tax_percent,
            'warning_level': get_warning_level(percent_tax, tax_percent)
        }


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


def group_issues_by_team(issues):
    grouping_key = lambda i: i.team
    return [(k, list(g)) for k, g in itertools.groupby(sorted(issues, key=grouping_key), key=grouping_key)]


def process(issues, url):
    compact_issues = map(compact, issues)
    print 'total issues: ', len(compact_issues)

    compact_issues_by_team = group_issues_by_team(compact_issues)

    ctx['teams'] = []
    ctx['teams_groups'] = {'default': []}
    ctx['filter_url'] = url

    for team_summary in gen_summaries(compact_issues_by_team):
        ctx['teams'].append(team_summary)

    ctx['teams'] = sorted(ctx['teams'], key=lambda team: team['name'])

    counted_teams = []
    for group_key, group_entries in ctx['groups'].iteritems():
        ctx['teams_groups'][group_key] = filter(lambda team: team['name'] in group_entries, ctx['teams'])
        counted_teams.extend(map(lambda team: team['name'], ctx['teams_groups'][group_key]))

    ctx['teams_groups']['default'] = filter(lambda team: team['name'] not in counted_teams, ctx['teams'])

    ctx['details'] = group_by_type(compact_issues_by_team)
    ctx['details'] = OrderedDict(sorted(ctx['details'].items()))

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
