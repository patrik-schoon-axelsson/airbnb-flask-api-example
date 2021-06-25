import os
# Environment-Vars for local handling
if os.path.exists("env.py"):
    import env
from bson.json_util import dumps
import logging
from flask import Flask, jsonify, request, render_template
from flask_pymongo import PyMongo
from bson.errors import InvalidId
from bson.objectid import ObjectId  

app = Flask(__name__)
app.config["MONGO_URI"] =  os.environ.get("MONGO_URI")
mongo = PyMongo(app)


""" 
    LOGGING HANDLER

Setting up logging for the deployed version of the app, so that
server-logs are available in a Heroku deployment where file-level
access is not present. 

"""

if __name__ != '__main__':
    print("Running on gunicorn logger!")
    gunicorn_logger = logging.getLogger('gunicorn.error')
    app.logger.handlers = gunicorn_logger.handlers
    app.logger.setLevel(gunicorn_logger.level)


@app.route('/', methods=['GET', 'POST'])
def main_entry():
    """

    Serves generic HTML documenting API endpoints and handles insertion-calls when it receives POST-requests
    with valid JSON data.

    """
    if request.method == "GET": 
        return render_template('index.html')
    elif request.method == "POST":
        try:
            collection = mongo.db.listingsAndReviews
            request_data = request.get_json()

            doc_post = {
                "name": request_data["name"],
                "description": request_data["description"],
                "listing_url": request_data["listing_url"]
            }
            new_doc = collection.insert_one(doc_post)

            app.logger.info((f'An incoming requestion from client {request.remote_addr} CREATED document {new_doc.inserted_id}'))

            return jsonify({"status": 200, "message": f"Succesfully added document {new_doc.inserted_id}"})
        except KeyError as ke:
            return jsonify({"status": 400, "error": "KeyError: This endpoint will only accept a JSON object with the following key-value pairs: 'name', 'description', 'listing_url'"})

@app.route('/api/', methods=['GET'])
def crud_all():
    
    """ 

    Accepts standard query-strings, for example: /api/?page_no=2&docs=10 where page_no is the page-offset into the collection and docs
    equals the amount of documents per page.


    A note on the pagination-process: I have elected to use the less performant "skip()" method of producing pagination by query-string
    due to time-constraints.
    This was only a choice made due to the limited use this API will see. In a production environment, a preferable option would
    be producing a filtering-algorithm based on the _id index, such as demonstrated in this blog-post: 
    
    https://www.codementor.io/@arpitbhayani/fast-and-efficient-pagination-in-mongodb-9095flbqr


    """

    if request.args.get('page_no') == None:
        page_no = 1
    else:
        try:
            page_no = int(request.args.get('page_no'))
        except ValueError:
            return jsonify({"status": 400, "error": "ValueError: 'page_no' query-parameter must be a number." })

    
    if request.args.get('docs') == None:
        docs = 15
    else:
        try:
            docs = int(request.args.get('docs'))
        except ValueError:
            return jsonify({"status": 400, "error": "ValueError: 'docs' query-parameter must be a number." })

    index = int(docs * page_no)

    collection = list(mongo.db.listingsAndReviews.find().skip(index).limit(docs))

    app.logger.info(f"Incoming request from {request.remote_addr} for paginator: Page No:  {page_no} & Docs: {docs}, index starts at {index}")
    return dumps(collection)

@app.route('/api/listings/<doc_id>', methods=['GET', 'DELETE', 'POST'])
def paginate_collection(doc_id):
    collection = mongo.db.listingsAndReviews
    """

    If-block handling the TypeErrors resulting from the sample_airbnb database using
    string-type for the "_id" field and new inserts from PyMongo being true MongoDB
    ObjectID types. For more information, see README.

    """
    if collection.find_one({ "_id": doc_id }) == None:
        try:
            doc_id = ObjectId(doc_id)
        except (InvalidId, TypeError):
            return jsonify({"status": 400, "error": "InvalidID or Type Error: This it not a valid BSON object-ID, nor is there a string match in the database for this ID."})

    if request.method == 'GET':
        # Get single-doc handler. Returns Error 404 on faulty ID-field, so no need to except errors.

        return dumps(collection.find_one_or_404({"_id": doc_id}))
    elif request.method == 'POST':
        """
        
        Update document handler. This being a proof-of-concept API, it only accepts values for the fields "listing_url", "name" and "description".

        Accepts application/json.
        
        """

        try:
            request_data = request.get_json()

            updates = {
            "listing_url": request_data["listing_url"],
            "name": request_data["name"],
            "description": request_data["description"]
            }
            doc = collection.update_one({"_id": doc_id}, { "$set": updates })

            app.logger.info((f'An incoming requestion from client {request.remote_addr} updated document {doc_id}'))
            return dumps(collection.find_one_or_404({"_id": doc_id}))
        except KeyError as ke:
            return jsonify({"status": 400, "error": "KeyError: This endpoint only accepts valid JSON with the key-value pairs: 'listing_url', 'name', 'description' "})


    elif request.method == 'DELETE':
        # Delete document handler
        if collection.find_one({"_id": doc_id}):
            collection.delete_one({"_id": doc_id})
            app.logger.warning((f'An incoming requestion from client {request.remote_addr} deleted document {doc_id}'))

            return jsonify({"status": 200, "message": f"Deleted document {doc_id}"})     
        else:
            return jsonify({"status": 404, "error": f"No item with ID field {doc_id}"})

if __name__ == '__main__':
    app.run(host=os.environ.get('IP'),
            port=int(os.environ.get('PORT')),
            debug=False)