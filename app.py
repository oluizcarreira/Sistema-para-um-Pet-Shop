# projeto_topicos_especiais/app.py

import os
from flask import Flask, render_template, request, redirect, url_for, session, flash
from pymongo import MongoClient, ASCENDING, DESCENDING
from bson.objectid import ObjectId
from datetime import datetime
from werkzeug.security import generate_password_hash, check_password_hash
import functools
from dotenv import load_dotenv

load_dotenv()

app = Flask(__name__)

app.secret_key = os.getenv('SECRET_KEY')

client = MongoClient(os.getenv('DATABASE_URL'))
db = client[os.getenv('DB')]
petshop_collection = db[os.getenv('COLPET')]
usuarios_collection = db[os.getenv('COLUSR')]

def login_required(view):
    @functools.wraps(view)
    def wrapped_view(**kwargs):
        if 'user_id' not in session:
            flash('Por favor, faça login para acessar esta página.', 'warning')
            return redirect(url_for('login'))
        return view(**kwargs)
    return wrapped_view

@app.route('/register', methods=['GET', 'POST'])
def register():
    if 'user_id' in session:
        return redirect(url_for('list_documents'))

    if request.method == 'POST':
        username = request.form.get('username','').strip()
        password = request.form.get('password')
        confirm_password = request.form.get('confirm_password')

        if not username or not password or not confirm_password:
            flash('Todos os campos são obrigatórios!', 'danger')
            return render_template('register.html', username=username)

        if password != confirm_password:
            flash('As senhas não coincidem!', 'danger')
            return render_template('register.html', username=username)

        if len(password) < 6:
            flash('A senha deve ter pelo menos 6 caracteres.', 'danger')
            return render_template('register.html', username=username)

        existing_user = usuarios_collection.find_one({'username_lower': username.lower()})
        if existing_user:
            flash('Este nome de usuário já existe. Tente outro.', 'danger')
            return render_template('register.html', username=username)

        hashed_password = generate_password_hash(password)
        usuarios_collection.insert_one({
            'username': username,
            'username_lower': username.lower(),
            'password': hashed_password,
            'created_at': datetime.utcnow()
        })
        
        flash('Cadastro realizado com sucesso! Faça login para continuar.', 'success')
        return redirect(url_for('login'))
    
    return render_template('register.html')

@app.route('/login', methods=['GET', 'POST'])
def login():
    if 'user_id' in session:
        return redirect(url_for('list_documents'))

    if request.method == 'POST':
        username = request.form.get('username','').strip()
        password = request.form.get('password')

        if not username or not password:
            flash('Nome de usuário e senha são obrigatórios!', 'danger')
            return render_template('login.html', username=username)

        user = usuarios_collection.find_one({'username_lower': username.lower()})

        if user and check_password_hash(user['password'], password):
            session['user_id'] = str(user['_id'])
            session['username'] = user['username']
            flash('Login realizado com sucesso!', 'success')
            return redirect(url_for('list_documents'))
        else:
            flash('Nome de usuário ou senha inválidos.', 'danger')
            return render_template('login.html', username=username)

    return render_template('login.html')

@app.route('/logout')
@login_required
def logout():
    session.pop('user_id', None)
    session.pop('username', None)
    flash('Você foi desconectado com segurança.', 'info')
    return redirect(url_for('login'))

@app.route('/')
def index():
    return redirect(url_for('welcome_page'))

@app.route('/welcome')
def welcome_page():
    return render_template('welcome.html')

# --- Rotas do CRUD Petshop (Protegidas) ---
@app.route('/list')
@login_required
def list_documents():
    search_query = request.args.get('search', default="", type=str)
    sort_by = request.args.get('sort_by', default="nome_animal", type=str)
    sort_order_str = request.args.get('sort_order', default="asc", type=str)
    tipo_animal_filter = request.args.get('tipo_animal', default="", type=str)
    data_nasc_inicio_filter = request.args.get('data_nasc_inicio', default="", type=str)
    data_nasc_fim_filter = request.args.get('data_nasc_fim', default="", type=str)

    if sort_order_str == 'desc':
        sort_order_mongo = DESCENDING
    else:
        sort_order_mongo = ASCENDING

    query_conditions = []

    if search_query:
        query_conditions.append({
            '$or': [
                {'nome_dono': {'$regex': search_query, '$options': 'i'}},
                {'nome_animal': {'$regex': search_query, '$options': 'i'}},
            ]
        })
    if tipo_animal_filter:
        query_conditions.append({'tipo_animal': {'$regex': tipo_animal_filter, '$options': 'i'}})

    date_nasc_conditions = {}
    if data_nasc_inicio_filter:
        try:
            inicio_dt = datetime.strptime(data_nasc_inicio_filter, '%Y-%m-%d')
            date_nasc_conditions['$gte'] = inicio_dt
        except ValueError:
            flash(f"Formato de data de início inválido: {data_nasc_inicio_filter}", 'warning')
    if data_nasc_fim_filter:
        try:
            fim_dt = datetime.strptime(data_nasc_fim_filter, '%Y-%m-%d')
            date_nasc_conditions['$lte'] = fim_dt
        except ValueError:
            flash(f"Formato de data de fim inválido: {data_nasc_fim_filter}", 'warning')
    if date_nasc_conditions:
        query_conditions.append({'data_nascimento_animal': date_nasc_conditions})

    final_query = {}
    if query_conditions:
        final_query['$and'] = query_conditions

    try:
        documents = list(petshop_collection.find(final_query).sort(sort_by, sort_order_mongo))
    except Exception as e:
        flash(f"Erro ao buscar e ordenar documentos: {e}", "danger")
        documents = []

    return render_template('list.html',
                           documents=documents,
                           search_query=search_query,
                           current_sort_by=sort_by,
                           current_sort_order=sort_order_str,
                           tipo_animal_filter=tipo_animal_filter,
                           data_nasc_inicio_filter=data_nasc_inicio_filter,
                           data_nasc_fim_filter=data_nasc_fim_filter)

@app.route('/detail/<id>')
@login_required
def detail(id):
    try:
        document = petshop_collection.find_one({'_id': ObjectId(id)})
        if not document:
            flash("Documento não encontrado.", 'warning')
            return redirect(url_for('list_documents'))
    except Exception as e:
        flash(f"Erro ao buscar detalhe do documento: {e}", 'danger')
        return redirect(url_for('list_documents'))
    return render_template('detail.html', document=document)

@app.route('/create', methods=['GET', 'POST'])
@login_required
def create():
    if request.method == 'POST':
        data = request.form
        try:
            data_nascimento_animal_str = data.get('data_nascimento_animal')
            data_nascimento_animal = datetime.strptime(data_nascimento_animal_str, '%Y-%m-%d') if data_nascimento_animal_str else None

            new_document = {
                'nome_dono': data.get('nome_dono'), 'cpf_dono': data.get('cpf_dono'),
                'tipo_animal': data.get('tipo_animal'), 'nome_animal': data.get('nome_animal'),
                'data_nascimento_animal': data_nascimento_animal,
                'raca_animal': data.get('raca_animal'), 'telefone': data.get('telefone'),
                'email': data.get('email'), 'endereco': data.get('endereco'),
                'bairro': data.get('bairro'), 'cidade': data.get('cidade'),
                'estado': data.get('estado'),
                'cadastrado_por_id': session.get('user_id'), # Armazena ID do usuário que cadastrou
                'cadastrado_por_username': session.get('username'), # Armazena username
                'data_cadastro': datetime.utcnow()
            }
            petshop_collection.insert_one(new_document)
            flash('Pet cadastrado com sucesso!', 'success')
            return redirect(url_for('list_documents'))
        except ValueError:
            flash("Erro: Formato de data inválido. Use YYYY-MM-DD.", 'danger')
            return render_template('create.html', data=data) # Retorna dados para o form
        except Exception as e:
            flash(f"Erro ao criar documento: {e}", 'danger')
            return render_template('create.html', data=data)
    return render_template('create.html', data={}) # Passa um dict vazio para o GET

@app.route('/edit/<id>', methods=['GET', 'POST'])
@login_required
def edit(id):
    try:
        document = petshop_collection.find_one({'_id': ObjectId(id)})
        if not document:
            flash("Documento não encontrado.", 'warning')
            return redirect(url_for('list_documents'))

        if request.method == 'POST':
            data = request.form
            try:
                data_nascimento_animal_str = data.get('data_nascimento_animal')
                data_nascimento_animal = datetime.strptime(data_nascimento_animal_str, '%Y-%m-%d') if data_nascimento_animal_str else None
                
                update_data = {
                    'nome_dono': data.get('nome_dono'), 'cpf_dono': data.get('cpf_dono'),
                    'tipo_animal': data.get('tipo_animal'), 'nome_animal': data.get('nome_animal'),
                    'data_nascimento_animal': data_nascimento_animal,
                    'raca_animal': data.get('raca_animal'), 'telefone': data.get('telefone'),
                    'email': data.get('email'), 'endereco': data.get('endereco'),
                    'bairro': data.get('bairro'), 'cidade': data.get('cidade'),
                    'estado': data.get('estado'),
                    'atualizado_em': datetime.utcnow(),
                    'atualizado_por_id': session.get('user_id'),
                    'atualizado_por_username': session.get('username')
                }
                petshop_collection.update_one({'_id': ObjectId(id)}, {'$set': update_data})
                flash('Cadastro atualizado com sucesso!', 'success')
                return redirect(url_for('detail', id=id))
            except ValueError:
                flash("Erro: Formato de data inválido ao editar. Use YYYY-MM-DD.", 'danger')
                # Prepara o documento para reenviar ao template
                if document.get('data_nascimento_animal') and isinstance(document['data_nascimento_animal'], datetime):
                    document['data_nascimento_animal_str'] = document['data_nascimento_animal'].strftime('%Y-%m-%d')
                else: # Se o dado original era inválido ou nulo, não tenta formatar
                    document['data_nascimento_animal_str'] = data_nascimento_animal_str # Mantém o que o usuário digitou
                return render_template('edit.html', document=document, id=id)
            except Exception as e:
                flash(f"Erro ao editar documento: {e}", 'danger')
                if document.get('data_nascimento_animal') and isinstance(document['data_nascimento_animal'], datetime):
                    document['data_nascimento_animal_str'] = document['data_nascimento_animal'].strftime('%Y-%m-%d')
                else:
                    document['data_nascimento_animal_str'] = data.get('data_nascimento_animal')
                return render_template('edit.html', document=document, id=id)
        
        # GET Request: Formata a data para exibição no formulário
        if document.get('data_nascimento_animal') and isinstance(document['data_nascimento_animal'], datetime):
            document['data_nascimento_animal_str'] = document['data_nascimento_animal'].strftime('%Y-%m-%d')
        return render_template('edit.html', document=document, id=id)

    except Exception as e:
        flash(f"Erro ao carregar dados para edição: {e}", 'danger')
        return redirect(url_for('list_documents'))

@app.route('/delete/<id>', methods=['POST'])
@login_required
def delete(id):
    try:
        result = petshop_collection.delete_one({'_id': ObjectId(id)})
        if result.deleted_count == 0:
            flash("Cadastro não encontrado para exclusão.", 'warning')
        else:
            flash('Cadastro excluído com sucesso!', 'success')
    except Exception as e:
        flash(f"Erro ao deletar cadastro: {e}", 'danger')
    return redirect(url_for('list_documents'))

if __name__ == '__main__':
    app.run(debug=True)