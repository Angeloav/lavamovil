
from flask import Flask, request, jsonify, redirect, url_for, session, render_template
import stripe

app = Flask(__name__)
app.config['SECRET_KEY'] = 'tu_clave_secreta'

stripe.api_key = 'sk_test_REEMPLAZA_CON_TU_CLAVE'

YOUR_DOMAIN = 'http://localhost:8080'  # O cambia esto al dominio real en producción

@app.route('/subscribe', methods=['GET'])
def show_subscribe_page():
    if 'user_id' not in session:
        return redirect(url_for('login'))
    return render_template('subscribe.html')

@app.route('/create-checkout-session', methods=['POST'])
def create_checkout_session():
    try:
        checkout_session = stripe.checkout.Session.create(
            payment_method_types=['card'],
            line_items=[
                {
                    'price_data': {
                        'currency': 'usd',
                        'product_data': {
                            'name': 'Suscripción LavaMóvil',
                        },
                        'unit_amount': 500,  # $5.00 USD
                    },
                    'quantity': 1,
                },
            ],
            mode='payment',
            success_url=YOUR_DOMAIN + '/success',
            cancel_url=YOUR_DOMAIN + '/cancel',
        )
        return redirect(checkout_session.url, code=303)
    except Exception as e:
        return jsonify(error=str(e)), 400

@app.route('/success')
def success():
    if 'user_id' in session:
        from app import db, Usuario
        user = db.session.get(Usuario, session['user_id'])
        if user:
            user.suscrito = True
            db.session.commit()
    return "¡Suscripción completada con éxito!"

@app.route('/cancel')
def cancel():
    return "Suscripción cancelada. Puedes intentarlo de nuevo cuando quieras."

if __name__ == "__main__":
    app.run(port=4242, debug=True)
