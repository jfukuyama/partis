#include "emm.h"

namespace ham {

// ----------------------------------------------------------------------------------------
emm::emm() {
  total_ = 0.0;
  tracks_ = NULL;
  track_indices = NULL;
  pair_ = false;
}

// ----------------------------------------------------------------------------------------
emm::~emm(){
  if (tracks_) delete tracks_;
}
  
// ----------------------------------------------------------------------------------------
void emm::parse(YAML::Node config, string is_pair, Tracks model_tracks) {
  scores.init();
  // NOTE at this point we only allow one track per emission (in particular, we require that pair emissions be on the same track). kinda TODO This'd be easy to change later, of course
  tracks_ = new vector<Track*>();  // list of the tracks used by *this* emission. Note that this may not be all the tracks used in the model.
  if (is_pair=="single") {
    pair_ = false;
    Track *tk(model_tracks.getTrack(config["track"].as<string>()));
    assert(tk);  // assures we actualy found the track in model_tracks
    tracks_->push_back(tk);
    scores.addTrack(tk, 0);
    
    YAML::Node probs(config["probs"]);
    assert(probs.size() == scores.getAlphaSize(0));  // TODO actually I don't need these either, since I'm looping over the track
    assert(scores.getAlphaSize(0) == tk->getAlphaSize()); // TODO arg I shouldn't need this. so complicated...
    vector<double> log_probs;
    total_ = 0.0; // make sure things add to 1.0
    for (size_t ip=0; ip<scores.getAlphaSize(0); ++ip) {
      double prob(probs[tk->getAlpha(ip)].as<double>());  // NOTE probs are stored as dicts in the file, so <probs> is unordered
      log_probs.push_back(log(prob));
      total_ += prob;
    }
    assert(fabs(total_-1.0) < EPS);  // TODO use something cleverer than a random hard coded EPS
    scores.AddColumn(log_probs);  // NOTE <log_probs> must already be logged
  } else if (is_pair=="pair") {
    pair_ = true;
    assert(config["tracks"].size() == 2);
    for (size_t it=0; it<config["tracks"].size(); ++it) {
      Track *tk(model_tracks.getTrack(config["tracks"][it].as<string>()));
      assert(tk);  // assures we actualy found the track in model_tracks
      tracks_->push_back(tk);
      scores.addTrack(tk, 0);
    }
    
    YAML::Node probs(config["probs"]);
    assert(probs.size() == scores.getAlphaSize(0));  // TODO actually I don't need these either, since I'm looping over the track
    assert(tracks_->size() == 2);
    assert(scores.getAlphaSize(0) == (*tracks_)[0]->getAlphaSize()); // TODO arg I shouldn't need this. so complicated...
    assert(scores.getAlphaSize(0) == (*tracks_)[1]->getAlphaSize()); // TODO arg I shouldn't need this. so complicated...
    total_ = 0.0; // make sure things add to 1.0
    for (size_t ip=0; ip<scores.getAlphaSize(0); ++ip) {
      YAML::Node these_probs(config["probs"][(*tracks_)[0]->getAlpha(ip)]);
      assert(these_probs.size() == scores.getAlphaSize(0));
      vector<double> log_probs;
      for (size_t ipp=0; ipp<scores.getAlphaSize(0); ++ipp) {
	double prob(these_probs[(*tracks_)[1]->getAlpha(ipp)].as<double>());  // NOTE probs are stored as dicts in the file, so <probs> is unordered
	log_probs.push_back(log(prob));
	total_ += prob;
      }
      scores.AddColumn(log_probs);  // NOTE <log_probs> must already be logged. also NOTE that a column in <scores> is maybe a row in the yaml file. I didn't choose it!
    }
    // TODO use something cleverer than a random hard coded EPS
    assert(fabs(total_-1.0) < EPS);  // make sure emissions probs sum to 1.0
  } else {
    assert(0);
  }
}
      
// ----------------------------------------------------------------------------------------
void emm::print() {
  for(size_t i=0; i<scores.getNTracks(); ++i)
    cout << "    " << scores.getTrack(i)->getName();
  cout << "     (normed to within at least " << EPS << ")" << endl;

  printf("%16s", "");
  // print name of each emission
  for (size_t ir=0; ir<(*tracks_)[0]->getAlphaSize(); ++ir)
    printf("%12s", (*tracks_)[0]->getAlpha(ir).c_str());
  // printf("        (total - 1.0 = %.5e - 1.0 = %.5e\n", total_, total_ - 1.0);
  cout << endl;

  if (!pair_) {
    assert(tracks_->size() == 1);
    printf("%16s", "");
    for (size_t ir=0; ir<(*tracks_)[0]->getAlphaSize(); ++ir) {
      double prob = exp(scores.getValue(ir));
      if (prob < 0.01)
	printf("%12.3e", exp(scores.getValue(ir)));
      else
	printf("%12.3f", exp(scores.getValue(ir)));
    }
    cout << "\n";
  } else {
    assert(tracks_->size() == 2);
    for (size_t ir=0; ir<(*tracks_)[0]->getAlphaSize(); ++ir) {
      printf("%16s", (*tracks_)[0]->getAlpha(ir).c_str());
      for (size_t ic=0; ic<(*tracks_)[1]->getAlphaSize(); ++ic)
	printf("%12.3e", exp(scores.getValue(ir, ic)));
      cout << "\n";
    }
  }
}

}
