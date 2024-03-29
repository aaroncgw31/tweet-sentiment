from.spacy import spacy_twitter_model

from sklearn.feature_extraction.text import CountVectorizer, TfidfVectorizer
from sklearn.decomposition import NMF, LatentDirichletAllocation
from sklearn.decomposition._nmf import _beta_divergence

import pickle
import datetime as dt

from warnings import simplefilter
from sklearn.exceptions import ConvergenceWarning
simplefilter("ignore", category=ConvergenceWarning)

nlp = spacy_twitter_model()


class TopicSeries:
    """
    Class that holds a time series of Topic models
    """
    def __init__(self, n_components=5, random_state=42):
        """
        Parameters:
            n_components: int, optional
                Number of topics for each topic model
            random_state: int, optional
                Random seed for NMF and LatentDirichletAllocation
        """
        self.n_components = n_components
        self.random_state = random_state
        self.cv_dict = {}
        self.tfidf_dict = {}
        self.nmf_dict = {}
        self.lda_dict = {}

    def calculate_nmf(self, date, data):
        """
        Fit TF-IDF and NMF models from Sklearn

        Parameters:
            date: string
                Date in 'yyyy-mm-dd' format
            data: Pandas DataFrame
                Data for a particular date range for the output of read_raw_data() method in modules.tweet_data
        """
        # TF-IDF model, token_pattern is alpha only words + hashtags
        tfidf = TfidfVectorizer(tokenizer=self.tokenizer, lowercase=False)
        tfidf_vecs = tfidf.fit_transform(data)
        # Fit NMF model with n_components topics with TF-IDF input
        nmf = NMF(n_components=self.n_components, random_state=self.random_state)
        nmf.fit_transform(tfidf_vecs)
        # Add TFIDF and NMF models to their respective dictionaries, with date as key
        self.tfidf_dict[date] = tfidf
        self.nmf_dict[date] = nmf

    def calculate_lda(self, date, data):
        """
        Fit CountVectorizer and LDA models from Sklearn

        Parameters:
            date: string
                Date in 'yyyy-mm-dd' format
            data: Pandas DataFrame
                Data for a particular date range for the output of read_raw_data() method in modules.tweet_data
        """
        # TF-IDF model, token_pattern is alpha only words + hashtags
        cv = CountVectorizer(tokenizer=self.tokenizer, lowercase=False)
        count_vecs = cv.fit_transform(data)
        # Fit LDA model with n_components topics with cv input
        lda = LatentDirichletAllocation(n_components=self.n_components, random_state=self.random_state)
        lda.fit_transform(count_vecs)
        # Add CountVectorizer and LDA models to their respective dictionaries, with date as key
        self.cv_dict[date] = cv
        self.lda_dict[date] = lda

    def fit(self, df, date_range):
        """
        Fit NMF and LDA models for a range of dates

        Parameters:
            df: Pandas DataFrame
                Data for a particular date range for the output of read_raw_data() method in modules.tweet_data
            date_range: DateTimeIndex
                DateTimeIndex of dates which will serve as range for fitting the data
        """

        for i in range(len(date_range) - 1):

            str_date = str(date_range[i + 1].date())
            print("Working on : ", str_date, end="\r")
            # Take portion of df in the range of a trading day
            sub_df = df[date_range[i]:(date_range[i + 1] - dt.timedelta(seconds=1))].tweet
            # Tokenize with Spacy NLP pipe. Disable tagger, parser and ner for faster calculation
            sub_df = [self.twitter_tokenizer(text) for text in nlp.pipe(sub_df, disable=["tagger", "parser", "ner"])]
            # Calculate NMF model
            self.calculate_nmf(str_date, sub_df)
            # Calculate LDA model
            self.calculate_lda(str_date, sub_df)

        print("\nFinished")

    def calc_rec_error(self, df, date_range):
        """
        Calculate reconstruction error. For the data of one trading day, take previous day's NMF
        model, apply transform method to the data, and calculate reconstruction error
        Parameters:
            df: Pandas DataFrame
                Data for a particular date range for the output of read_raw_data() method in modules.tweet_data
            date_range: DateTimeIndex
                DateTimeIndex of dates which will serve as range for fitting the data

        Returns: list, list
                List of reconstruction errors for the fitted models
                List of reconstruction errors for the transformed data
        """

        model_err = []
        new_err = []

        for i in range(len(date_range) - 1):
            str_date = str(date_range[i + 1].date())
            prev_str_date = str(date_range[i].date())
            print("Working on : ", str_date, end="\r")

            # Take portion of df in the range of a trading day
            sub_df = df[date_range[i]:(date_range[i + 1] - dt.timedelta(seconds=1))].tweet
            # Tokenize with Spacy NLP pipe. Disable tagger, parser and ner for faster calculation
            sub_df = [self.twitter_tokenizer(text) for text in nlp.pipe(sub_df, disable=["tagger", "parser", "ner"])]
            # Use previous day's tfidf model to transform data to tfidf format used to fit NMF model
            tfidf_vecs = self.tfidf_dict[prev_str_date].transform(sub_df)
            # Calculate reconstruction error using method from
            # https://github.com/scikit-learn/scikit-learn/blob/master/sklearn/decomposition/_nmf.py
            new_rec_err = _beta_divergence(tfidf_vecs,
                                           self.nmf_dict[prev_str_date].transform(tfidf_vecs),
                                           self.nmf_dict[prev_str_date].components_,
                                           'frobenius',
                                           square_root=True)
            # Reconstruction error from original model
            rec_err = self.nmf_dict[str_date].reconstruction_err_

            model_err.append(rec_err)
            new_err.append(new_rec_err)

        print("\nFinished")

        return model_err, new_err

    def save(self, file_path='data/topics.p'):

        pickle.dump(self, open(file_path, "wb"))

    @staticmethod
    def tokenizer(d):
        return d

    @staticmethod
    def twitter_tokenizer(doc,
                          urls=True,
                          stop_words=True,
                          lowercase=True,
                          alpha_only=True,
                          hashtags=False,
                          lemma=False):
        """
        Full tokenizer with flags for processing steps

        Parameters:
            urls: bool, optional
                If True, remove URLs
            stop_words: bool, optional
                If True, removes stop words
            lowercase: bool, optional
                If True, lowercases all tokens
            alpha_only: bool, optional
                If True, removes all non-alpha characters
            hashtags: bool, optional
                If True, remove hashtags
            lemma: bool, optional
            If True, lemmatizes words

        Returns:
            List[str]
                List of tokens
        """
        # token collector
        tokens = []
        for t in doc:
            # remove URLs
            if t.like_url or t._.is_piclink & urls:
                continue
            # only include stop words if stop words==True
            if t.is_stop & stop_words:
                continue
            # if alpha_only=True, only include alpha characters unless they are hashtags
            if not t.is_alpha & alpha_only:
                # only include hashtags if hashtags=True
                if hashtags:
                    continue
                else:
                    if not t._.is_hashtag:
                        continue
            if lemma:
                t = t.lemma_
            else:
                t = t.text
            if lowercase:
                t = t.lower()
            tokens.append(t)
        return tokens


def display_components(model, word_features, top_display=5):
    """
    Displays the top words by probability in each topic of a topic model

    Parameters:
        model: Sklearn topic model such as LatentDirichletAllocation or NMF
        word_features:
            Output from get_feature_names() method from count vectorizer used to fit model
        top_display: int, optional
            Number of words per topic displayed
    """
    for topic_idx, topic in enumerate(model.components_):
        print("Topic {}:".format(topic_idx))
        top_words_idx = topic.argsort()[::-1][:top_display]
        top_words = [word_features[i] for i in top_words_idx]
        print(" ".join(top_words))
