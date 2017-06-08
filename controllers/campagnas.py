# -*- coding: utf-8 -*-
from flask import (
    Blueprint,
    current_app,
    Response,
    abort,
    jsonify,
    request,
    session,
    redirect,
    flash,
    render_template,
    url_for
)
from flask_login import login_required, current_user
from sqlalchemy import Table
import mailchimp
from utils import get_mailchimp_api
from eventos import get_event_data
from time import timezone
from datetime import datetime, timedelta
import json

campagnas = Blueprint('campagnas', __name__)


def initialize_app(app):
    app.register_blueprint(campagnas)


@campagnas.route("/campagnas", methods=['GET', 'POST'])
@login_required
def index(message=None, folder=None, page=0):
    data = {
        'qty': 0,
        'lists': [],
        'message': message,
        'current_folder': folder,
        'page': page
    }
    return render_template('campagnas/list.html', title="NOMBRE", **data)

@campagnas.route("/campagnas/ajax/listar", methods=['GET', 'POST'])
@login_required
def ajax_listar_campagnas():
    m = get_mailchimp_api()
    campaignList = m.campaigns.list()
    return json.dumps(campaignList)


@campagnas.route("/campagnas/ajax/folders", methods=['GET', 'POST'])
def ajax_folder_list():
    return json.dumps(get_mailchimp_api().folders.list("campaign"))


@campagnas.route("/campagnas/page/<page>", methods=['GET', 'POST'])
@login_required
def page(page=None):
    return index(None, None, page)


@campagnas.route("/campagnas/folder/<folder>/page/<page>",
                 methods=['GET', 'POST'])
@login_required
def pageAndFolder(folder=None, page=None):
    return index(None, folder, page)


@campagnas.route("/campagnas/folder/<folder>", methods=['GET', 'POST'])
@login_required
def folder(folder=None):
    return index(None, folder)


@campagnas.route("/campagnas/folder/setArea", methods=['POST'])
@login_required
def changeFolder():
    folder_id = request.form['area']
    id_camp = request.form['id']
    try:
        m = get_mailchimp_api()
        details = m.campaigns.update(id_camp, 'options',
                                     {'folder_id': folder_id})
    except mailchimp.Error, e:
        return "Ha ocurrido un error con mailchimp", e

    return index(None, details['data']['folder_id'])


@campagnas.route("/campagnas/folder/add/", methods=['POST'])
@login_required
def addFolder():
    name = request.form['name']
    folderType = "campaign"
    try:
        m = get_mailchimp_api()
        folder_id = m.folders.add(name, folderType)
    except mailchimp.Error, e:
        return "Ha ocurrido un error al intentar conectar con mailchimp"
    return index(None, folder_id)


@campagnas.route("/campagnas/create", methods=['GET'])
@login_required
def create():
    try:
        m = get_mailchimp_api()
        lists = m.lists.list(sort_field='web')
        template_lists = m.templates.list()
        folderList = m.folders.list("campaign")
    except mailchimp.Error, e:
        return "Ha ocurrido un error con mailchimp<br>"+str(e)
    from models import events, posts
    # join = events.join(posts, events.c.post_id == posts.c.ID)
    # event_list = events.select().select_from(join).execute()
    event_list = []
    data = {
        'eventList': event_list,
        'lists': lists['data'],
        'template_lists': template_lists['user'],
        'areaList': folderList
    }
    return render_template('campagnas/create.html',
                           title="Crear campañas",
                           **data)


@campagnas.route("/campagnas/create", methods=['POST'])
@login_required
def create2():
    type = 'regular'
    options = {
        'list_id': request.form['emailList'],
        'subject': request.form['subject'],
        'from_email': request.form['outgoinEmail'],
        'from_name': request.form['outgoinName'],
        'title': request.form['campaignName'],
        'auto_footer': False,
        'folder_id': request.form['folder']
    }
    event_id = int(request.form['event_id'])
    content = {
        'html': request.form['html']
    }
    if (event_id > 0):
        event_data = get_event_data(event_id)
        content = {
            'html': replace_tags(request.form['html'], event_data)
        }
    m = get_mailchimp_api()
    try:
        if 'id' in request.form:
            cid = request.form['id']
            detailsVar = m.campaigns.update(cid, 'options', options)
            details2 = m.campaigns.update(cid, 'content', content)
            errors = detailsVar['errors']
            detailsVar = detailsVar['data']
        else:
            detailsVar = m.campaigns.create(type, options, content)
    except mailchimp.Error, e:
        return index("<div class='alert alert-danger'>Ha ocurrido un error \
                      con mailchimp "+str(e)+"</div>")
    return details(detailsVar["id"])


@campagnas.route("/campagnas/detalles/<id>", methods=['GET'])
@login_required
def details(id):
    try:
        m = get_mailchimp_api()
        details = m.campaigns.list({'campaign_id': id})
        lists = m.lists.list()

    except mailchimp.Error, e:
        return index("Ha ocurrido un error con mailchimp"+str(e))
    campaign = details['data'][0]
    current_list = None
    set_current_gmt(campaign)
    for emailList in lists['data']:
        if campaign["list_id"] == emailList["id"]:
            current_list = emailList
    if campaign['status'] == "sent":
        campaign['status'] = "Enviado"
    elif campaign['status'] == "save":
        campaign['status'] = "Guardado"
    elif campaign['status'] == "sending":
        campaign['status'] = "Enviando"
    data = {
        'campaign': campaign,
        'lists': lists['data'],
        'current_list': current_list
    }
    return render_template('campagnas/details.html',
                           title="Detalles",
                           **data)


@campagnas.route("/campagnas/edit/<id>", methods=['GET'])
@login_required
def edit(id):
    try:
        m = get_mailchimp_api()
        details = m.campaigns.list({'campaign_id': id})
        content = m.campaigns.content(id)
        lists = m.lists.list()
        template_lists = m.templates.list()
        folderList = m.folders.list("campaign")
    except mailchimp.Error, e:
        return index("Ha ocurrido un error con mailchimp"+str(e))
    from models import events, posts
    join = events.join(posts, events.c.post_id == posts.c.ID)
    event_list = events.select().select_from(join).execute()

    html = (clean_html(content['html']))

    data = {
        'campaign': details['data'][0],
        'html': html,
        'eventList': event_list,
        'lists': lists['data'],
        'template_lists': template_lists['user'],
        'areaList': folderList
    }
    return render_template('campagnas/edit.html',
                           title="Editar campaña",
                           **data)


@campagnas.route("/campagnas/clone/<id>", methods=['GET'])
@login_required
def clone(id):
    try:
        m = get_mailchimp_api()
        details = m.campaigns.list({'campaign_id': id})
        content = m.campaigns.content(id)
        lists = m.lists.list()
        template_lists = m.templates.list()
        folderList = m.folders.list("campaign")
    except mailchimp.Error, e:
        return index("Ha ocurrido un error con mailchimp"+str(e))
    from models import events, posts
    # join = events.join(posts, events.c.post_id == posts.c.ID)
    # event_list = events.select().select_from(join).execute()
    event_list = []
    html = replace_rewards_unsubcribe(content['html'])
    details['data'][0]['id'] = None
    data = {
        'campaign': details['data'][0],
        'html': html,
        'eventList': event_list,
        'lists': lists['data'],
        'template_lists': template_lists['user'],
        'areaList': folderList
    }
    return render_template('campagnas/edit.html',
                           title="Editar campaña",
                           **data)


@campagnas.route("/campagnas/send", methods=['POST'])
@login_required
def send():
    id = request.form['id']
    try:
        m = get_mailchimp_api()
        status = m.campaigns.send(id)
    except mailchimp.Error, e:
        message = "<div class='alert alert-danger'>"
        message += "Se encontraron errores con mailchimp "
        message += str(e)+"</div>"
        return index(message)
    return details(id)


@campagnas.route("/campagnas/sendTest", methods=['POST'])
@login_required
def sendTest():
    emails = request.form.getlist('email')
    campaingId = request.form['campaignId']
    try:
        m = get_mailchimp_api()
        details = m.campaigns.send_test(campaingId, emails)
    except mailchimp.Error, e:
        message = "<div class='alert alert-danger'>"
        message += "Se encontraron errores con mailchimp "
        message += str(e)+"</div>"
        return index(message)
    message = "<div class='alert alert-succes'>"
    message += "pruebas enviadas correctamente"
    message += "</div>"
    return index(message)


@campagnas.route("/campagnas/delete", methods=['POST'])
@login_required
def delete():
    id_ = request.form['id']
    try:
        print id_ 
        print "entra try"
        m = get_mailchimp_api()
        status = m.campaigns.delete(id_)
    except mailchimp.CampaignDoesNotExistError:
        return index("<div class='alert alert-danger'>\
                      Error, no existe</div>")
    except mailchimp.Error, e:
        return "Ha ocurrido un error con mailchimp", e
    message = "<div class='alert alert-success'>"
    message += "Eliminado Correctamente</div>"
    return index(message)


def replace_tags(html, data):
    html = html.replace("*|EVENT_NAME|*", data['event_name'])
    html = html.replace("*|EVENT_DATE|*", str(data['event_start_date']))
    html = html.replace("http://*|EVENT_URL|*", data['url'])
    html = html.replace("*|EVENT_URL|*", data['url'])

    if html.find('*|REWARDS|*') < 0:
        html += '<div style="display:none">*|REWARDS|*</div>'
    return html


def replace_rewards_unsubcribe(html):
    from bs4 import BeautifulSoup
    soup = BeautifulSoup(html)
    url_rewards = 'http://www.mailchimp.com/monkey-rewards'
    url_unsubcribe = '.com/unsubscribe'
    url_archive = 'campaign-archive'
    for link in soup.findAll('a'):
        if url_rewards in link.get('href', ''):
            link.findParent().decompose()
        if url_unsubcribe in link.get('href', ''):
            link['href'] = '*|UNSUB|*'
        if url_archive in link.get('href', ''):
            link['href'] = '*|ARCHIVE|*'
    return unicode(soup)


def set_current_gmt(campaign):
    format = "%Y-%m-%d %H:%M:%S"
    keys = ['create_time', 'send_time']
    for key in keys:
        if campaign[key]:
            new_date = datetime.strptime(campaign[key], format)
            campaign[key] = new_date - timedelta(seconds=timezone)
    return campaign


def clean_html(html):
    from BeautifulSoup import BeautifulSoup
    html = replace_rewards_unsubcribe(html)
    soup = BeautifulSoup(html)
    mailchimp_datas = soup.findAll('table', {'id': 'canspamBarWrapper'})
    for data in mailchimp_datas:
        data.findParent().decompose()
    return unicode(soup )
